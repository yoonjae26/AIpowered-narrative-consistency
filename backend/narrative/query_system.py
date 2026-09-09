from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.narrative.character.memory_system import CharacterMemorySystem
from backend.narrative.korean_text import (
    extract_character_query_name,
    extract_character_identity_query_name,
    extract_relationship_query_name,
    normalize_korean_text,
)
from backend.narrative.mutation.models import RetrievalProfile
from backend.narrative.reasoning.reasoning_graph import ReasoningGraph, ReasoningGraphBuilder
from backend.narrative.relationships.graph import RelationshipGraph
from backend.rag import NarrativeMemoryService
from backend.version_control.event_store import EventStore

# Intent string → RetrievalProfile — single place to change routing logic
_INTENT_TO_PROFILE: dict[str, RetrievalProfile] = {
    "NARRATIVE":     RetrievalProfile.NARRATIVE,
    "HISTORY":       RetrievalProfile.NARRATIVE,
    "PREDICTION":    RetrievalProfile.REASONING,
    "MOTIVATION":    RetrievalProfile.CHARACTER,
    "RELATIONSHIP":  RetrievalProfile.CHARACTER,
    "IDENTITY":      RetrievalProfile.REASONING,   # bare name → all sources
}

# ── Verifier constants ──────────────────────────────────────────────────────
# Source reliability: how authoritative is each retrieval source?
_SOURCE_RELIABILITY: dict[str, float] = {
    "KG": 0.99,     # direct graph lookup — near-certain
    "PBKD": 0.91,   # character profile — authored, stable
    "Memory": 0.82, # semantic search hit — weighted by retrieval score
    "World": 0.95,  # lore rules — explicit but may be incomplete
}

# Role factor: how much epistemic weight does the node's role carry?
_ROLE_CONFIDENCE_FACTOR: dict[str, float] = {
    "ground_truth": 1.00,
    "motivation":   0.90,
    "evidence":     0.85,
    "constraint":   1.00,
    "hypothesis":   0.45,  # speculative — must use uncertainty language
}

# Hard conflicts: factual impossibilities regardless of context.
# Matching means the derived claim is logically incompatible with ground truth — blocks `passed`.
# Example: KG says character is dead; GPT infers they spoke → reject.
_HARD_CONTRADICTION_PAIRS: list[tuple[str, str]] = [
    (
        r"dead|사망|죽었|죽음|deceased|killed",
        r"말했|대화|행동|등장|나타났|움직|said|spoke|appeared|moved|acts|walked",
    ),
    # Directional relationship inversion: A→B parent cannot also be B→A parent
    (
        r"(?P<a>\w+)의 아버지|(?P<b>\w+) is parent of",
        r"아버지는 (?P=a)|(?P=b) is child of",
    ),
]

# Soft conflicts: contextual tension — may be valid in counterfactual/speculative contexts.
# Example: KG ally; GPT speculates "may support another side" — warn, do not reject.
_SOFT_CONTRADICTION_PAIRS: list[tuple[str, str]] = [
    (r"ally|동맹|alliance",     r"enemy|적|hatred|혐오|싫"),
    (r"trust|신뢰|믿",          r"betray|배신|불신|의심"),
    (r"friend|친구|우정",        r"enemy|적대|혐오|싫어"),
]


def _dedup_hits(hits: list, threshold: float = 0.55) -> list:
    """Remove near-duplicate retrieval hits using character bigram Jaccard similarity.

    Keeps the first (highest-scored) hit from each near-duplicate cluster.
    threshold=0.55 means >55% shared bigrams → duplicate.
    Effective against scenes indexed multiple times with minor differences.
    """
    kept = []
    for hit in hits:
        content = hit.content
        bigrams_a = {content[i:i+2] for i in range(len(content) - 1)}
        is_dup = False
        for k in kept:
            kc = k.content
            bigrams_b = {kc[i:i+2] for i in range(len(kc) - 1)}
            union = bigrams_a | bigrams_b
            if union and len(bigrams_a & bigrams_b) / len(union) > threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(hit)
    return kept


@dataclass(slots=True)
class QueryAnswer:
    query: str
    answer: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    reasoning_graph: dict[str, Any] | None = None


@dataclass
class VerifierConfig:
    """Central configuration for all verification thresholds.

    Separating these from hardcoded literals lets operators tune the system
    without touching logic — e.g. lower answer_support_threshold during
    early prototyping, raise it as the embedding model improves.
    """
    # ── Answer faithfulness (Step 1 / 4) ─────────────────────────────────────
    answer_support_threshold: float = 0.65   # hybrid score below this → unsupported
    semantic_weight: float = 0.70            # cosine similarity weight in hybrid score
    lexical_weight: float = 0.30             # bigram Jaccard weight in hybrid score
    min_sentence_length: int = 12            # skip sentences shorter than this (chars)
    # ── Retrieval deduplication (Step 3) ─────────────────────────────────────
    dedup_threshold: float = 0.55            # bigram Jaccard above this → duplicate hit
    # ── Adaptive score filtering (Step 3) ────────────────────────────────────
    score_cutoff: float = 0.70               # best_score below this → use low threshold
    score_threshold_low: float = 0.10        # when best_score < score_cutoff
    score_threshold_high: float = 0.60       # when best_score >= score_cutoff — must be < score_cutoff to avoid filtering hits that barely triggered high mode
    # ── Claim consistency (Step 3) ───────────────────────────────────────────
    explicit_confidence_min: float = 0.90    # explicit/GT claims for conflict detection
    derived_confidence_max: float = 0.60     # derived/inference claims for conflict detection


class NarrativeQuerySystem:
    """Structured query layer over story state, memory, graph, and event history."""

    def __init__(
        self,
        character_repo: CharacterRepository,
        lore_repo: LoreRepository,
        scene_repo: SceneRepository,
        relationship_graph: RelationshipGraph,
        memory_service: NarrativeMemoryService,
        event_store: EventStore,
    ) -> None:
        self._characters = character_repo
        self._lore = lore_repo
        self._scenes = scene_repo
        self._graph = relationship_graph
        self._memory = CharacterMemorySystem(character_repo)
        self._memory_service = memory_service
        self._event_store = event_store
        self._verifier_config = VerifierConfig()
        # Cache: hash(tuple(texts)) → list of embedding vectors
        # Facts within one story session rarely change per query, so this avoids
        # re-encoding the same sentences on every verification call.
        self._fact_embedding_cache: dict[int, list[list[float]]] = {}

    def query(self, query_text: str) -> QueryAnswer:
        """Route to the appropriate handler by query type.

        Query type classification:
          IDENTITY     — X는 어떤 사람? X의 성격? → character_profile()
          RELATIONSHIP — X가 신뢰하는 인물은? X의 동맹은? → KG dimension query (or semantic fallback)
          MOTIVATION   — X는 왜 Y? → semantic_query() [PBKD priority]
          NARRATIVE    — X는 지금 무엇을? → semantic_query() [Memory priority]
        """
        q = query_text.strip()
        if trait_check := self._extract_character_trait_confirmation_query(q):
            return self.confirm_character_trait(trait_check[0], trait_check[1])
        if descriptor := self._extract_trait_who_query(q):
            return self.who_has_trait(descriptor)

        # IDENTITY: only route when extracted name is a known character (not a generic noun)
        if name := extract_character_identity_query_name(q):
            if self._find_character(name) is not None:
                return self.character_profile(name)

        if topic := self._extract_known_topic(q):
            return self.who_knows_about(topic)
        if pair := self._extract_relationship_pair(q):
            return self.relationship_between(pair[0], pair[1])
        if name := self._extract_status_target(q):
            return self.status_of(name)
        if name := self._extract_location_target(q):
            return self.where_is(name)
        if name := self._extract_event_target(q):
            return self.what_happened_to(name)
        if relation_query := self._extract_dimension_query(q):
            return self.relationship_dimension_query(relation_query[0], relation_query[1])

        # RELATIONSHIP (Korean): explicit KG-first routing — Relationship Query is the
        # foundation for reasoning, not a fallback.
        if rel_name := extract_relationship_query_name(q):
            dimension = self._detect_relationship_dimension(q)
            if dimension:
                kg_result = self.relationship_dimension_query(dimension, rel_name)
                if kg_result.evidence:
                    # KG had graph data — pass it as seed context to semantic reasoning
                    return self.semantic_query(q, kg_seed=kg_result)
            # No graph data or no dimension detected — semantic with KG context still applies

        # RELATIONSHIP / MOTIVATION / NARRATIVE → Level 3 reasoning
        return self.semantic_query(q)

    def who_has_trait(self, descriptor: str) -> QueryAnswer:
        canonical = self._canonicalize_descriptor_query(descriptor)
        matches: list[dict[str, Any]] = []

        for character in self._characters.list():
            memory = self._memory.get_memory(character.name)
            trait_events = list(memory.trait_events)
            pending_events = list(memory.pending_trait_events)
            all_events = [(item, False) for item in trait_events] + [(item, True) for item in pending_events]

            matched_items: list[dict[str, Any]] = []
            for item, is_pending in all_events:
                if not self._trait_matches_query(item, descriptor, canonical):
                    continue
                matched_items.append({
                    "trait": item.get("trait"),
                    "relation": item.get("relation"),
                    "surface": item.get("surface"),
                    "confidence": item.get("confidence"),
                    "pending": is_pending,
                })

            if not matched_items:
                continue

            matches.append({
                "character": character.name,
                "matches": matched_items[:8],
            })

        if not matches:
            return QueryAnswer(
                query=f"who is {descriptor}",
                answer="현재 기억에서 해당 특성에 맞는 인물이 없습니다.",
                evidence=[],
            )

        names = ", ".join(item["character"] for item in matches)
        return QueryAnswer(
            query=f"who is {descriptor}",
            answer=names,
            evidence=matches,
        )

    def confirm_character_trait(self, name: str, descriptor: str) -> QueryAnswer:
        character = self._find_character(name)
        if character is None:
            return QueryAnswer(query=f"is {name} {descriptor}", answer="인물을 찾을 수 없습니다.")

        memory = self._memory.get_memory(character.name)
        canonical = self._canonicalize_descriptor_query(descriptor)
        permanent_matches: list[dict[str, Any]] = []
        pending_matches: list[dict[str, Any]] = []

        for item in memory.trait_events:
            if self._trait_matches_query(item, descriptor, canonical):
                permanent_matches.append(item)
        for item in memory.pending_trait_events:
            if self._trait_matches_query(item, descriptor, canonical):
                pending_matches.append(item)

        if permanent_matches:
            return QueryAnswer(
                query=f"is {name} {descriptor}",
                answer=f"{character.name}은(는) {descriptor}(으)로 묘사됩니다.",
                evidence=[
                    {
                        "character": character.name,
                        "match_type": "permanent",
                        "matches": permanent_matches[:8],
                    }
                ],
            )

        if pending_matches:
            return QueryAnswer(
                query=f"is {name} {descriptor}",
                answer=f"부분적으로 일치합니다. {character.name}이(가) {descriptor}일 수 있다는 보류 중인 증거가 있으나 신뢰도가 아직 충분하지 않습니다.",
                evidence=[
                    {
                        "character": character.name,
                        "match_type": "pending",
                        "matches": pending_matches[:8],
                    }
                ],
            )

        return QueryAnswer(
            query=f"is {name} {descriptor}",
            answer=f"{character.name}이(가) {descriptor}라는 강한 증거가 아직 없습니다.",
            evidence=[],
        )

    def character_profile(self, name: str) -> QueryAnswer:
        character = self._find_character(name)
        if character is None:
            return QueryAnswer(query=f"character profile of {name}", answer="인물을 찾을 수 없습니다.")

        memory = self._memory.get_memory(character.name)
        trait_events = list(memory.trait_events)[-8:]
        pending_trait_events = list(memory.pending_trait_events)[-8:]
        traits = [str(item.get("trait")) for item in trait_events if item.get("trait")]
        pending_traits = [str(item.get("trait")) for item in pending_trait_events if item.get("trait")]
        personality = [item for item in memory.personality if item]
        beliefs = [item for item in memory.beliefs if item]
        summary_bits: list[str] = []
        if traits:
            summary_bits.append("traits=" + ", ".join(sorted(dict.fromkeys(traits))))
        if pending_traits:
            summary_bits.append("pending_traits=" + ", ".join(sorted(dict.fromkeys(pending_traits))))
        if personality:
            summary_bits.append("personality=" + ", ".join(personality[:4]))
        if beliefs:
            summary_bits.append("beliefs=" + ", ".join(beliefs[:3]))
        if not summary_bits:
            summary_bits.append("아직 뚜렷한 내부 프로필 신호가 없습니다.")

        return QueryAnswer(
            query=f"character profile of {name}",
            answer=f"{character.name}: " + " | ".join(summary_bits),
            evidence=[
                {
                    "name": character.name,
                    "status": character.status,
                    "trait_events": trait_events,
                    "pending_trait_events": pending_trait_events,
                    "memory": memory.as_dict(),
                }
            ],
        )

    def who_knows_about(self, topic: str) -> QueryAnswer:
        matches: list[dict[str, Any]] = []
        lowered = topic.lower()
        for character in self._characters.list():
            memory = self._memory.get_memory(character.name)
            corpus = memory.knowledge + memory.beliefs
            if any(lowered in item.lower() for item in corpus):
                matches.append({
                    "character": character.name,
                    "knowledge": [item for item in corpus if lowered in item.lower()],
                })
        if matches:
            names = ", ".join(item["character"] for item in matches)
            return QueryAnswer(query=f"Who knows about {topic}?", answer=names, evidence=matches)
        return QueryAnswer(query=f"Who knows about {topic}?", answer="명시적인 지식 정보가 없습니다.", evidence=[])

    def relationship_between(self, source: str, target: str) -> QueryAnswer:
        edge = self._graph.relationship_between(source, target)
        if edge is None:
            return QueryAnswer(query=f"relationship between {source} and {target}", answer="직접적인 관계가 없습니다.")
        answer = f"{source} -> {target}: {edge.relationship_type.value} (strength {edge.strength:.2f})"
        return QueryAnswer(query=f"relationship between {source} and {target}", answer=answer, evidence=[{
            "source": edge.source,
            "target": edge.target,
            "relationship_type": edge.relationship_type.value,
            "strength": edge.strength,
            "dimensions": edge.dimensions,
        }])

    def status_of(self, name: str) -> QueryAnswer:
        for character in self._characters.list():
            if character.name.lower() == name.lower():
                metadata = character.metadata_json or {}
                return QueryAnswer(
                    query=f"status of {name}",
                    answer=f"{character.name}의 현재 상태: {character.status}",
                    evidence=[{"status": character.status, "metadata": metadata}],
                )
        return QueryAnswer(query=f"status of {name}", answer="인물을 찾을 수 없습니다.")

    def _detect_relationship_dimension(self, query: str) -> str | None:
        """Map Korean/English relationship keywords to KG dimension names."""
        if any(kw in query for kw in ["신뢰", "믿", "trust"]):
            return "trust"
        if any(kw in query for kw in ["동맹", "alliance"]):
            return "alliance"
        if any(kw in query for kw in ["친구", "우정", "friendship", "friend"]):
            return "friendship"
        if any(kw in query for kw in ["적대", "혐오", "hate", "hatred"]):
            return "hatred"
        return None

    _BARE_NAME_RE = re.compile(r'^[가-힣A-Za-z0-9·_\-]{2,8}$')

    def _classify_intent(self, query: str) -> str:
        """Rule-based intent classification — input to ReasoningGraphBuilder."""
        if any(kw in query for kw in ["신뢰", "동맹", "관계", "적대", "trust", "alliance", "relationship", "friendship", "동료", "가장 가까운"]):
            return "RELATIONSHIP"
        if any(kw in query for kw in ["왜", "이유", "동기", "목표", "why", "motivation", "goal", "원하는", "바라는"]):
            return "MOTIVATION"
        if any(kw in query for kw in ["과거", "일어난", "사건", "history", "happened", "event", "했었", "있었"]):
            return "HISTORY"
        if any(kw in query for kw in ["앞으로", "미래", "예측", "앞날", "향후", "predict", "future"]):
            return "PREDICTION"
        # Bare character/place name (2-8 chars, no particles or action words) → character lookup
        bare = re.sub(r'(은|는|이|가|의|을|를)$', '', normalize_korean_text(query).strip()).strip()
        if self._BARE_NAME_RE.fullmatch(bare):
            return "IDENTITY"
        return "NARRATIVE"

    def semantic_query(self, query_text: str, kg_seed: QueryAnswer | None = None) -> QueryAnswer:
        """Level 3 reasoning: Intent → ReasoningGraph → Retrieve → GPT(explain) → Verify.

        Key architectural difference from before:
        - ReasoningGraphBuilder builds a DAG of source nodes with roles.
        - ground_truth nodes (KG for RELATIONSHIP, PBKD for MOTIVATION) drive the answer.
        - GPT explains/narrates; it does not decide the answer when ground truth exists.
        """
        intent = self._classify_intent(query_text)
        routed_name = extract_character_query_name(query_text)
        normalized_query = normalize_korean_text(query_text)
        character_names = [routed_name] if routed_name else []

        profile = _INTENT_TO_PROFILE.get(intent, RetrievalProfile.REASONING)

        # Build reasoning graph — determines what to retrieve and what role each source plays
        graph = ReasoningGraphBuilder().build(query_text, intent, character_names)

        hits = self._memory_service.search_hierarchy(
            normalized_query,
            character_name=routed_name,
            limit=6,
            profile=profile,
        )

        # Adaptive threshold: keyword-only fallback (hash embedder) gives [0,1] overlap scores;
        # real embeddings give cosine ~0.6-0.95. Lower threshold when best score < score_cutoff.
        cfg = self._verifier_config
        best_score = max((h.score for h in hits), default=0.0)
        score_threshold = (
            cfg.score_threshold_low if best_score < cfg.score_cutoff
            else cfg.score_threshold_high
        )
        filtered_hits = _dedup_hits(
            [h for h in hits if h.score >= score_threshold],
            threshold=cfg.dedup_threshold,
        )

        if not filtered_hits:
            return QueryAnswer(
                query=query_text,
                answer="이 쿼리에 대한 관련 기억을 찾을 수 없습니다.",
                evidence=[],
            )

        kg_context = self._build_kg_context(character_names)
        pbkd_context = self._build_pbkd_context(character_names)
        narrative_context = "\n\n".join(f"[{h.source_type}] {h.content}" for h in filtered_hits[:3])

        # Inject pre-computed KG traversal result as authoritative seed
        if kg_seed and kg_seed.evidence:
            seed_lines = "\n".join(
                f"  {e.get('source', '')} --[{e.get('relationship_type', '')}]--> "
                f"{e.get('target', '')} (dimensions={e.get('dimensions', {})})"
                for e in kg_seed.evidence
                if isinstance(e, dict) and "source" in e
            )
            if seed_lines:
                kg_context = f"[KG 직접 조회 — 이 결과는 GROUND TRUTH]\n{seed_lines}\n\n{kg_context}".strip()

        # Best retrieval score per source — Memory uses semantic search scores;
        # KG/PBKD are direct lookups (treated as score=1.0).
        retrieval_scores: dict[str, float] = {"KG": 1.0, "PBKD": 1.0}
        for hit in filtered_hits:
            retrieval_scores["Memory"] = max(
                retrieval_scores.get("Memory", 0.0), hit.score
            )

        reasoning = self._synthesize_answer(
            query_text, narrative_context, pbkd_context, kg_context,
            graph=graph,
            fallback=filtered_hits[0].content,
        )

        verified = self._verify_answer(
            reasoning, kg_context, pbkd_context, narrative_context,
            graph=graph, retrieval_scores=retrieval_scores,
            hits=filtered_hits,
        )

        evidence: list[dict[str, Any]] = [
            {
                "id": hit.id,
                "source_type": hit.source_type,
                "score": round(hit.score, 4),
                "content": hit.content,
                "title": hit.metadata.get("title") or None,
            }
            for hit in filtered_hits
        ]
        if reasoning.get("facts") or reasoning.get("inferences"):
            evidence.append({
                "reasoning": {
                    "intent": intent,
                    "graph": [
                        {
                            "source": n.source,
                            "role": n.role,
                            "support_type": n.support_type,
                            "hint": n.query_hint,
                            "confidence": n.confidence,
                        }
                        for n in graph.ordered_nodes
                    ],
                    "facts": reasoning["facts"],
                    "inferences": reasoning["inferences"],
                    "uncertainty": reasoning["uncertainty"],
                    "missing_information": reasoning["missing_information"],
                    "verification": verified,
                }
            })

        return QueryAnswer(
            query=query_text,
            answer=reasoning["answer"],
            evidence=evidence,
            reasoning_graph=graph.to_dict(),
        )

    def _build_pbkd_context(self, character_names: list[str]) -> str:
        """Build PBKD profile context for named characters."""
        if not character_names:
            return ""
        parts: list[str] = []
        for name in character_names:
            char = self._find_character(name)
            if char is None:
                continue
            meta = char.metadata_json if isinstance(char.metadata_json, dict) else {}
            traits = list(char.traits or [])
            goals = list(char.goals or [])
            beliefs = [str(b) for b in (meta.get("beliefs") or [])]
            knowledge = [str(k) for k in (meta.get("knowledge") or [])]
            desires = [str(d) for d in (meta.get("desires") or goals)]
            lines: list[str] = []
            if traits:
                lines.append(f"  성격(P): {', '.join(traits)}")
            if beliefs:
                lines.append(f"  신념(B): {', '.join(beliefs)}")
            if knowledge:
                lines.append(f"  지식(K): {', '.join(knowledge)}")
            if desires:
                lines.append(f"  욕망/목표(D): {', '.join(desires)}")
            if lines:
                parts.append(f"[{char.name} PBKD]\n" + "\n".join(lines))
        return "\n\n".join(parts)

    def _build_kg_context(self, character_names: list[str]) -> str:
        """Build relationship context from the graph for named characters."""
        if not character_names:
            return ""
        lines: list[str] = []
        for name in character_names:
            char = self._find_character(name)
            if char is None:
                continue
            edges = self._graph.list_relationships(char.id)
            for edge in edges[:8]:
                src_name = self._resolve_char_name(edge.source) or edge.source
                tgt_name = self._resolve_char_name(edge.target) or edge.target
                lines.append(f"  {src_name} --[{edge.relationship_type.value}]--> {tgt_name} (강도 {edge.strength:.1f})")
        if not lines:
            return ""
        return "[인물 관계]\n" + "\n".join(lines)

    def _resolve_char_name(self, char_id: str) -> str | None:
        for char in self._characters.list():
            if char.id == char_id:
                return char.name
        return None

    @property
    def _embedder(self):
        """Return the shared embedder from the memory service, or None if unavailable."""
        try:
            return self._memory_service._search.semantic_search.embedder
        except AttributeError:
            return None

    def _get_fact_embeddings(self, texts: list[str]) -> list[list[float]] | None:
        """Encode texts into sentence vectors, with instance-level caching.

        Cache key = hash(tuple(texts)).  Same facts across repeated queries
        within one session → zero re-encoding cost.
        Returns None when the embedder is unavailable (graceful degradation to
        lexical-only verification).
        """
        if not texts:
            return []
        embedder = self._embedder
        if embedder is None:
            return None
        cache_key = hash(tuple(texts))
        if cache_key in self._fact_embedding_cache:
            return self._fact_embedding_cache[cache_key]
        try:
            raw = embedder.embed(texts)
            # Normalise to list[list[float]] regardless of numpy/list return type
            vecs: list[list[float]] = [
                v.tolist() if hasattr(v, "tolist") else list(v) for v in raw
            ]
            self._fact_embedding_cache[cache_key] = vecs
            return vecs
        except Exception:
            return None

    def _compute_hybrid_support(
        self,
        sent_vec: list[float] | None,
        sent: str,
        fact_sentences: list[str],
        fact_embeddings: list[list[float]] | None,
    ) -> tuple[float, int | None, dict[str, Any]]:
        """Hybrid semantic + lexical support score for one answer sentence.

        Returns (hybrid_score, best_fact_index, score_components).
        score_components = {"cosine": float|None, "lexical": float, "hybrid": float}
        Semantic = cosine similarity against pre-encoded fact embeddings.
        Lexical  = character bigram Jaccard (catches exact term / number matches
                   that embedding similarity may miss).
        Falls back to pure lexical when sent_vec or fact_embeddings are None.
        """
        if not fact_sentences:
            return 0.0, None, {"cosine": None, "lexical": 0.0, "hybrid": 0.0}

        cfg = self._verifier_config
        sent_bigrams = {sent[i:i+2] for i in range(len(sent) - 1)}

        # ── Lexical pass ─────────────────────────────────────────────────────
        lex_scores: list[float] = []
        for fs in fact_sentences:
            fb = {fs[i:i+2] for i in range(len(fs) - 1)}
            union = sent_bigrams | fb
            lex_scores.append(len(sent_bigrams & fb) / len(union) if union else 0.0)

        max_lex = max(lex_scores) if lex_scores else 0.0
        best_lex_idx: int | None = lex_scores.index(max_lex) if lex_scores else None

        # ── Semantic pass ─────────────────────────────────────────────────────
        if sent_vec is not None and fact_embeddings:
            try:
                import numpy as np
                sv = np.array(sent_vec, dtype=float)
                sv_norm = float(np.linalg.norm(sv))
                if sv_norm > 0:
                    cos_scores: list[float] = []
                    for fv in fact_embeddings:
                        fv_arr = np.array(fv, dtype=float)
                        fv_norm = float(np.linalg.norm(fv_arr))
                        cos_scores.append(
                            float(sv @ fv_arr) / (sv_norm * fv_norm) if fv_norm > 0 else 0.0
                        )
                    max_cos = max(cos_scores)
                    best_cos_idx = cos_scores.index(max_cos)
                    hybrid = cfg.semantic_weight * max_cos + cfg.lexical_weight * max_lex
                    best_idx: int | None = best_cos_idx if max_cos >= max_lex else best_lex_idx
                    components = {
                        "cosine": round(max_cos, 3),
                        "lexical": round(max_lex, 3),
                        "hybrid": round(hybrid, 3),
                    }
                    logger.debug(
                        "hybrid_support sent=%r cos=%.3f lex=%.3f hybrid=%.3f best_fact=%r",
                        sent[:60], max_cos, max_lex, hybrid,
                        fact_sentences[best_idx][:60] if best_idx is not None else None,
                    )
                    return hybrid, best_idx, components
            except Exception:
                pass

        # Fallback: lexical only
        components = {"cosine": None, "lexical": round(max_lex, 3), "hybrid": round(max_lex, 3)}
        return max_lex, best_lex_idx, components

    def _attribute_sentence_to_node(
        self,
        best_fact_idx: int | None,
        facts: list[dict[str, Any]],
        graph: ReasoningGraph,
    ) -> dict[str, Any] | None:
        """Map a supported answer sentence to the Reasoning Graph node that produced it.

        Uses the best-matching fact's source field (KG / PBKD / Memory) to find the
        graph node.  Among nodes with the same source, prefers nodes by role priority:
        ground_truth > evidence > motivation > hypothesis > constraint.
        Returns None when attribution cannot be determined.
        """
        if best_fact_idx is None or best_fact_idx >= len(facts):
            return None
        fact_source = str(facts[best_fact_idx].get("source") or "")
        if not fact_source:
            return None
        _role_prio = {
            "ground_truth": 0, "evidence": 1, "motivation": 2,
            "constraint": 3, "hypothesis": 4,
        }
        matching = [n for n in graph.ordered_nodes if n.source == fact_source]
        if not matching:
            return None
        best_node = min(matching, key=lambda n: _role_prio.get(n.role, 5))
        return {
            "node_id": best_node.node_id,
            "source": best_node.source,
            "role": best_node.role,
            "query_hint": best_node.query_hint,
        }

    def _synthesize_answer(
        self,
        query: str,
        narrative_context: str,
        pbkd_context: str,
        kg_context: str,
        graph: ReasoningGraph | None = None,
        fallback: str = "",
    ) -> dict[str, Any]:
        """Explainable Narrative Reasoning Engine driven by a ReasoningGraph.

        Ground-truth nodes in the graph constrain GPT: it explains, does not decide.
        Returns dict: answer, facts, inferences, uncertainty, missing_information.
        """
        _empty = {"answer": fallback, "facts": [], "inferences": [], "uncertainty": False, "missing_information": []}
        try:
            import json as _json
            from backend.llm.providers import create_llm_provider
            from backend.llm.providers.base import LLMMessage
            provider = create_llm_provider()

            intent = graph.intent if graph else "NARRATIVE"
            gt_sources = graph.ground_truth_sources() if graph else []
            plan_text = graph.as_plan_text() if graph else ""

            # Ground-truth authority rule — generated dynamically from graph
            gt_rule = ""
            if "KG" in gt_sources:
                gt_rule = (
                    "Rule GT-KG — KG 데이터는 GROUND TRUTH이다. "
                    "GPT는 KG 결과를 바탕으로 답을 결정하는 것이 아니라 "
                    "'KG에 따르면 ...'으로 인용하고 PBKD/Memory로 설명만 한다. "
                    "KG 결과와 다른 결론 도출 금지.\n"
                )
            elif "PBKD" in gt_sources:
                gt_rule = (
                    "Rule GT-PBKD — PBKD는 캐릭터 동기의 GROUND TRUTH이다. "
                    "GPT는 PBKD에 명시된 Belief/Desire/Goal을 인용하고 "
                    "Memory/KG로 맥락을 추가한다. PBKD 외 동기 추론 금지.\n"
                )
            elif "Memory" in gt_sources:
                gt_rule = (
                    "Rule GT-Memory — Memory의 사실 기록은 GROUND TRUTH이다. "
                    "GPT는 Memory 사실을 변경하거나 반박할 수 없다.\n"
                )

            # Hypothesis rule — injected when graph contains speculative nodes
            hyp_nodes = graph.hypothesis_nodes() if graph else []
            if hyp_nodes:
                min_conf = min(n.confidence for n in hyp_nodes)
                gt_rule += (
                    f"Rule GT-Hyp — 가설 노드(confidence={min_conf:.2f})에서 나온 주장은 단정 금지. "
                    "'가능성이 있다', '가정하면', '추론하면' 표현 필수. "
                    "JSON uncertainty=true로 표시.\n"
                )

            system_prompt = (
                "당신은 NarrativeOS의 서사 추론 엔진(Explainable Narrative Reasoning Engine)이다.\n"
                "목적: 캐릭터, 세계관, 사건, 관계에 대한 질문에 답변한다.\n"
                "모든 답변은 반드시 제공된 데이터에 근거해야 하며, 외부 지식이나 일반 상식을 사용해서는 안 된다.\n\n"
                f"현재 쿼리 유형: {intent}\n"
                f"{gt_rule}"
                "정보 우선순위: Knowledge Graph(KG) > PBKD > Narrative Memory\n\n"
                "핵심 규칙:\n"
                "Rule 1 — 제공된 KG/PBKD/Memory만 사용. 외부 지식, 일반 상식, 장르 관습 금지.\n"
                "Rule 2 — 캐릭터 특성은 PBKD 또는 KG에 명시된 경우에만 사용.\n"
                "Rule 3 — '기사는 용감하다' 등 상식 기반 추론 금지.\n"
                "Rule 4 — 관계는 KG 또는 PBKD에 존재할 때만 사용.\n"
                "Rule 5 — KG 관계 존재 시 반드시 명시적으로 언급.\n"
                "Rule 6 — 모든 결론은 KG/PBKD/Memory 중 하나에 추적 가능해야 함.\n"
                "Rule 7 — Inference 시 '추론하면', '가능성이 있다', '근거에 따르면' 중 하나 사용.\n"
                "Rule 8 — 근거 부족 시 '알 수 없다. 제공된 정보만으로는 판단할 수 없다.'로 답.\n"
                "Rule 9 — Hallucination 금지.\n"
                "Rule 10 — answer 작성 순서 (반드시 준수):\n"
                "  1단계 [사실]: Memory/KG에서 확인된 내용을 변형 없이 인용. 추론 금지.\n"
                "    예: 'Memory에 따르면 카엘은 오린과 앞으로의 행동을 논의하고 있다.'\n"
                "  2단계 [배경, 선택적]: PBKD의 Belief/Desire/Goal 중 관련 항목을 인용.\n"
                "    예: 'PBKD에 기록된 카엘의 신념은 \"약자를 지켜야 한다\"이다.'\n"
                "  3단계 [추론, 선택적]: 사실+배경에서 도출되는 추론. '가능성이 있다', '따라서 ~일 수 있다' 필수.\n"
                "    예: '따라서 그의 행동은 약자 보호와 관련될 가능성이 있다.'\n"
                "  사실·추론 혼합 금지. 추론을 사실인 것처럼 서술하는 것은 Rule 위반이다.\n\n"
                "출력 형식 (반드시 JSON):\n"
                '{"answer": "...", "facts": [{"source": "KG|PBKD|Memory", "content": "..."}], '
                '"inferences": [{"reasoning": "...", "based_on": ["..."]}], '
                '"uncertainty": false, "missing_information": []}'
            )

            input_parts: list[str] = [f"User Query\n{query}"]
            if plan_text:
                input_parts.append(plan_text)
            if kg_context:
                input_parts.append(f"Knowledge Graph\n{kg_context}")
            if pbkd_context:
                input_parts.append(f"PBKD\n{pbkd_context}")
            input_parts.append(f"Narrative Memory\n{narrative_context}")
            user_content = "\n\n".join(input_parts)

            response = provider.complete(
                [
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_content),
                ],
                max_tokens=700,
            )
            raw = response.content.strip()
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                parsed = _json.loads(json_match.group())
                return {
                    "answer": str(parsed.get("answer") or fallback),
                    "facts": parsed.get("facts") or [],
                    "inferences": parsed.get("inferences") or [],
                    "uncertainty": bool(parsed.get("uncertainty", False)),
                    "missing_information": parsed.get("missing_information") or [],
                }
            return {"answer": raw, "facts": [], "inferences": [], "uncertainty": False, "missing_information": []}
        except Exception:
            return _empty

    def _verify_answer(
        self,
        reasoning: dict[str, Any],
        kg_context: str,
        pbkd_context: str,
        narrative_context: str,
        graph: "ReasoningGraph | None" = None,
        retrieval_scores: dict[str, float] | None = None,
        hits: list | None = None,
    ) -> dict[str, Any]:
        """Heuristic verifier — no extra LLM call.

        Confidence is computed dynamically:
          confidence = source_reliability × retrieval_factor × role_factor × support_bonus
        See _SOURCE_RELIABILITY, _ROLE_CONFIDENCE_FACTOR, _compute_claim_confidence().

        Answer faithfulness uses hybrid semantic (cosine) + lexical (bigram Jaccard)
        similarity.  Each answer sentence is checked against the GPT-extracted facts
        corpus, and attributed to the Reasoning Graph node that produced the best-
        matching fact (Step 5+6).
        """
        grounded_in: list[str] = []
        if kg_context:
            grounded_in.append("KG")
        if pbkd_context:
            grounded_in.append("PBKD")
        if narrative_context:
            grounded_in.append("Memory")

        source_support: dict[str, str] = {}
        source_to_roles: dict[str, set[str]] = {}
        if graph:
            for node in graph.nodes:
                source_support[node.source] = node.support_type
                source_to_roles.setdefault(node.source, set()).add(node.role)

        _context_available: dict[str, bool] = {
            "KG": bool(kg_context),
            "PBKD": bool(pbkd_context),
            "Memory": bool(narrative_context),
        }

        support_count = len(grounded_in)
        facts: list[dict[str, Any]] = reasoning.get("facts") or []
        claims: list[dict[str, Any]] = []
        unverifiable: list[str] = []

        # ── Claim-level verification (Step 5) ────────────────────────────────
        # Each GPT-extracted fact is checked for traceability and assigned a
        # dynamic confidence score.  Facts whose source is not in the retrieved
        # context are flagged as unverifiable.
        for fact in facts:
            source = str(fact.get("source") or "")
            content = str(fact.get("content") or "")
            support_type = source_support.get(source, "derived")
            traceable = (
                source in _context_available
                and _context_available.get(source, False)
            )
            if not traceable:
                unverifiable.append(content[:80])

            conf = self._compute_claim_confidence(
                source, source_to_roles, retrieval_scores or {}, support_count
            )

            # Attribution: which graph node does this fact come from?
            node_attr: dict[str, Any] | None = None
            if graph and source:
                node_attr = self._attribute_sentence_to_node(
                    # facts list index = current position — use len(claims) as proxy
                    len(claims), facts, graph,
                )

            claims.append({
                "claim": content[:120],
                "support": [{"type": support_type, "source": source}] if source else [],
                "confidence": conf,
                "verified": traceable,
                "attributed_node": node_attr,
            })

        chain_result = (
            self._verify_reasoning_chain(claims, graph, source_to_roles)
            if graph else {"reasoning_chain_valid": True, "chain_violations": []}
        )
        consistency = self._check_claim_consistency(claims)

        # ── Answer faithfulness: hybrid semantic + lexical (Steps 1, 4, 5, 6) ──
        # For every sentence in the answer:
        #   1. Compute hybrid support score against the GPT-extracted facts corpus.
        #   2. Flag sentences below the threshold as unsupported.
        #   3. Attribute each sentence to the Reasoning Graph node whose fact
        #      best matches it (evidence attribution).
        cfg = self._verifier_config
        answer_text = str(reasoning.get("answer", ""))

        # ── Expand facts to sub-sentences for fine-grained matching ──────────
        # Each fact content may span multiple sentences; comparing a single
        # answer sentence against a long passage dilutes both cosine and bigram
        # scores. We split each fact into individual sentences and keep a reverse
        # mapping back to the original fact index for attribution.
        _sent_splitter = re.compile(r"(?<=[.!?。])\s+|\n")
        fact_sub_sentences: list[str] = []   # individual sentences extracted from facts
        fact_parent_idx: list[int] = []      # fact_sub_sentences[i] came from facts[fact_parent_idx[i]]
        for fi, f in enumerate(facts):
            content = str(f.get("content", ""))
            if not content:
                continue
            sub_sents = [s.strip() for s in _sent_splitter.split(content) if len(s.strip()) >= 6]
            if not sub_sents:
                sub_sents = [content]
            for ss in sub_sents:
                fact_sub_sentences.append(ss)
                fact_parent_idx.append(fi)

        # Batch-encode facts once (cached) and all answer sentences at once.
        fact_embeddings = self._get_fact_embeddings(fact_sub_sentences)
        answer_sentences: list[str] = [
            s.strip()
            for s in _sent_splitter.split(answer_text)
            if len(s.strip()) >= cfg.min_sentence_length
        ]
        sent_embeddings = self._get_fact_embeddings(answer_sentences)

        logger.debug(
            "faithfulness_check: %d answer sents, %d fact sub-sents (from %d facts)",
            len(answer_sentences), len(fact_sub_sentences), len(facts),
        )

        sentence_faithfulness: list[dict[str, Any]] = []
        unsupported_in_answer: list[str] = []

        for i, sent in enumerate(answer_sentences):
            sent_vec = sent_embeddings[i] if sent_embeddings and i < len(sent_embeddings) else None
            support_score, best_sub_idx, score_components = self._compute_hybrid_support(
                sent_vec, sent, fact_sub_sentences, fact_embeddings
            )
            # Map sub-sentence index back to original fact index for attribution
            best_fact_idx: int | None = (
                fact_parent_idx[best_sub_idx]
                if best_sub_idx is not None and best_sub_idx < len(fact_parent_idx)
                else None
            )
            is_supported = support_score >= cfg.answer_support_threshold

            if not is_supported:
                unsupported_in_answer.append(sent[:120])

            # Evidence attribution: trace the sentence back to its graph node
            node_attr = (
                self._attribute_sentence_to_node(best_fact_idx, facts, graph)
                if graph and best_fact_idx is not None else None
            )

            entry: dict[str, Any] = {
                "sentence": sent[:120],
                "support_score": round(support_score, 3),
                "is_supported": is_supported,
                "score_components": score_components,  # cosine / lexical / hybrid for debugging
            }
            if best_sub_idx is not None and best_sub_idx < len(fact_sub_sentences):
                entry["best_supporting_fact"] = fact_sub_sentences[best_sub_idx][:100]
            if node_attr:
                entry["attributed_node"] = node_attr
            sentence_faithfulness.append(entry)

        return {
            "grounded_in": grounded_in,
            "claims": claims,
            "unverifiable_claims": unverifiable,
            "passed": (
                len(unverifiable) == 0
                and chain_result["reasoning_chain_valid"]
                and consistency["claim_consistency_valid"]  # only hard conflicts block
            ),
            "reasoning_chain_valid": chain_result["reasoning_chain_valid"],
            "chain_violations": chain_result["chain_violations"],
            "claim_consistency_valid": consistency["claim_consistency_valid"],
            "claim_conflicts": consistency["claim_conflicts"],
            "soft_warnings": consistency["soft_warnings"],
            "answer_faithfulness": sentence_faithfulness,
            "answer_unsupported_claims": unsupported_in_answer,  # backward compat
        }

    def _compute_claim_confidence(
        self,
        source: str,
        source_to_roles: dict[str, set[str]],
        retrieval_scores: dict[str, float],
        support_count: int,
    ) -> float:
        """Dynamic confidence = source_reliability × retrieval_factor × role_factor × support_bonus.

        source_reliability — how authoritative the source is (see _SOURCE_RELIABILITY)
        retrieval_factor   — semantic search score for Memory; 1.0 for KG/PBKD (exact lookup)
        role_factor        — epistemic weight of the node's role (hypothesis penalised to 0.45)
        support_bonus      — each additional grounded source adds +8%, capped at 3 extras
        """
        base = _SOURCE_RELIABILITY.get(source, 0.70)
        retrieval_factor = retrieval_scores.get(source, 1.0) if source == "Memory" else 1.0
        roles = source_to_roles.get(source, {"motivation"})
        role_factor = min(_ROLE_CONFIDENCE_FACTOR.get(r, 0.70) for r in roles)
        support_bonus = 1.0 + 0.08 * min(support_count - 1, 3)
        return round(min(base * retrieval_factor * role_factor * support_bonus, 0.99), 3)

    def _check_claim_consistency(
        self,
        claims: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Heuristic contradiction detector — no LLM call.

        Two severity levels:
          hard — factual impossibility regardless of context (e.g., dead ↔ acted).
                 Blocks `passed`. Frontend should show as error.
          soft — contextual tension valid in counterfactual/speculative contexts
                 (e.g., ally ↔ may support another side).
                 Does NOT block `passed`. Frontend shows as warning.

        Compares high-confidence explicit claims (≥0.90) against low-confidence
        derived claims (<0.60). Outside that band the comparison is skipped.
        """
        cfg = self._verifier_config
        explicit_claims = [c for c in claims if c.get("confidence", 0) >= cfg.explicit_confidence_min]
        derived_claims  = [c for c in claims if c.get("confidence", 0) < cfg.derived_confidence_max]

        conflicts: list[dict[str, str]] = []
        for exp in explicit_claims:
            exp_text = exp.get("claim", "")
            for der in derived_claims:
                der_text = der.get("claim", "")
                for pos_pat, neg_pat in _HARD_CONTRADICTION_PAIRS:
                    try:
                        if (re.search(pos_pat, exp_text, re.IGNORECASE) and
                                re.search(neg_pat, der_text, re.IGNORECASE)):
                            conflicts.append({
                                "explicit_claim": exp_text[:100],
                                "conflicting_claim": der_text[:100],
                                "severity": "hard",
                            })
                    except re.error:
                        pass
                for pos_pat, neg_pat in _SOFT_CONTRADICTION_PAIRS:
                    if (re.search(pos_pat, exp_text, re.IGNORECASE) and
                            re.search(neg_pat, der_text, re.IGNORECASE)):
                        conflicts.append({
                            "explicit_claim": exp_text[:100],
                            "conflicting_claim": der_text[:100],
                            "severity": "soft",
                        })

        hard_conflicts = [c for c in conflicts if c["severity"] == "hard"]
        return {
            "claim_consistency_valid": len(hard_conflicts) == 0,
            "claim_conflicts": conflicts,
            "hard_conflicts": hard_conflicts,
            "soft_warnings": [c for c in conflicts if c["severity"] == "soft"],
        }

    def _verify_reasoning_chain(
        self,
        claims: list[dict[str, Any]],
        graph: "ReasoningGraph",
        source_to_roles: dict[str, set[str]] | None = None,
    ) -> dict[str, Any]:
        """Heuristic chain validator — no LLM call.

        Valid chain: ground_truth → motivation/evidence → hypothesis
        Violations:
          hypothesis_without_anchor — LLM inferred hypothesis without citing any GT source
          chain_skip                — LLM jumped GT → hypothesis, skipping the middle layer
                                      (only flagged when the graph planned a middle layer)
        """
        violations: list[str] = []

        if source_to_roles is None:
            source_to_roles = {}
            for node in graph.nodes:
                source_to_roles.setdefault(node.source, set()).add(node.role)

        gt_sources: set[str] = {s for s, roles in source_to_roles.items() if "ground_truth" in roles}
        mid_sources: set[str] = {s for s, roles in source_to_roles.items() if roles & {"motivation", "evidence"}}
        hyp_exists: bool = any("hypothesis" in roles for roles in source_to_roles.values())

        if not hyp_exists:
            return {"reasoning_chain_valid": True, "chain_violations": []}

        cited_sources: set[str] = {
            sup.get("source", "")
            for claim in claims
            for sup in claim.get("support", [])
            if sup.get("source")
        }

        if gt_sources and not (cited_sources & gt_sources):
            violations.append(
                f"hypothesis_without_anchor: 가설 추론이 있지만 GROUND TRUTH 출처 "
                f"({', '.join(sorted(gt_sources))})가 인용되지 않음"
            )

        if mid_sources and not (cited_sources & mid_sources):
            violations.append(
                f"chain_skip: 중간 단계({', '.join(sorted(mid_sources))})를 건너뛰고 "
                "가설로 직접 연결됨 — motivation/evidence 없이 가설 단정 불가"
            )

        return {
            "reasoning_chain_valid": len(violations) == 0,
            "chain_violations": violations,
        }

    def where_is(self, name: str) -> QueryAnswer:
        replay = self._event_store.replay_state()
        characters = replay.get("characters", {})
        if name in characters:
            location = characters[name].get("last_location")
            if location:
                return QueryAnswer(query=f"where is {name}", answer=f"{name}의 현재 위치: {location}.", evidence=[characters[name]])
            inferred = self._infer_location_from_memory(name)
            if inferred is not None:
                return QueryAnswer(
                    query=f"where is {name}",
                    answer=f"의미 검색 기준으로 {name}은(는) {inferred['location']}에 있는 것으로 추정됩니다.",
                    evidence=[characters[name], inferred],
                )
            return QueryAnswer(query=f"where is {name}", answer=f"{name}의 위치 정보가 없습니다.", evidence=[characters[name]])
        return QueryAnswer(query=f"where is {name}", answer="인물을 찾을 수 없습니다.")

    def what_happened_to(self, name: str) -> QueryAnswer:
        events = [event for event in self._event_store.list_events() if event.subject.lower() == name.lower() or (event.target or "").lower() == name.lower()]
        if not events:
            return QueryAnswer(
                query=f"what happened to {name}",
                answer="사건 기록이 없습니다.",
                evidence=[]
            )

        summary = "\n".join(
            f"- {getattr(e, 'happened_at', getattr(e, 'recorded_at', '?'))}: {e.predicate}"
            for e in events[-5:]
        )

        return QueryAnswer(
            query=f"what happened to {name}",
            answer=summary,
            evidence=[
                {
                    "id": e.id,
                    "predicate": e.predicate,
                    "branch": e.branch
                }
                for e in events[-5:]
            ]
        )

    def relationship_dimension_query(self, dimension: str, name: str | None = None) -> QueryAnswer:
        edges = self._graph.query_by_dimension(dimension, minimum=0.5)
        if name:
            edges = [edge for edge in edges if edge.source.lower() == name.lower() or edge.target.lower() == name.lower()]
        if not edges:
            return QueryAnswer(query=f"{dimension} query", answer=f"'{dimension}' 차원의 관계를 찾을 수 없습니다.")
        summary = "; ".join(
            f"{edge.source}->{edge.target} {dimension}={edge.dimensions.get(dimension, 0.0):.2f}"
            for edge in edges[:10]
        )
        return QueryAnswer(
            query=f"{dimension} query",
            answer=summary,
            evidence=[
                {
                    "source": edge.source,
                    "target": edge.target,
                    "relationship_type": edge.relationship_type.value,
                    "dimensions": edge.dimensions,
                }
                for edge in edges[:10]
            ],
        )

    def _extract_known_topic(self, query: str) -> str | None:
        patterns = [
            r"누가\s*(?P<topic>[가-힣A-Za-z0-9\s]+?)(?:을|를|에 대해)?\s*(?:알고|알아)(?:\s*있|는지)?",
            r"(?P<topic>[가-힣A-Za-z0-9\s]+?)(?:을|를)\s*아는\s*(?:인물|캐릭터)",
            r"who knows about (?P<topic>.+)$",
            r"who is aware of (?P<topic>.+)$",
            r"which characters know about (?P<topic>.+)$",
            r"who has knowledge of (?P<topic>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("topic").strip(" ?")
        return None

    def _extract_trait_who_query(self, query: str) -> str | None:
        normalized = normalize_korean_text(query).strip(" ?")
        korean_patterns = [
            r"^(?P<descriptor>[가-힣A-Za-z0-9_\s]+?)\s*(?:사람|애|캐릭터)?\s*누구(?:야|예요|인가요)?$",
            r"^(?P<descriptor>[가-힣A-Za-z0-9_\s]+?)\s*(?:인|한)\s*사람\s*누구(?:야|예요|인가요)?$",
        ]
        for pattern in korean_patterns:
            match = re.search(pattern, normalized)
            if match:
                return match.group("descriptor").strip()
        return None

    def _extract_character_trait_confirmation_query(self, query: str) -> tuple[str, str] | None:
        normalized = normalize_korean_text(query).strip(" ?")
        patterns = [
            r"^(?P<name>[가-힣A-Za-z0-9_]{2,}?)\s*(?:은|는|이|가)?\s*(?P<descriptor>[가-힣A-Za-z0-9_\s]+?)\s*(?:사람)?\s*맞아(?:요)?$",
            r"^(?P<name>[가-힣A-Za-z0-9_]{2,}?)\s*(?:은|는|이|가)?\s*(?P<descriptor>[가-힣A-Za-z0-9_\s]+?)\s*(?:사람)?\s*맞지(?:요)?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                name = re.sub(r"(은|는|이|가)$", "", match.group("name").strip())
                descriptor = match.group("descriptor").strip()
                if name and descriptor:
                    return name, descriptor
        return None

    def _canonicalize_descriptor_query(self, descriptor: str) -> str:
        key = self._descriptor_key(descriptor)
        alias_map = {
            "재밌": "funny",
            "재미있": "funny",
            "웃긴": "funny",
            "예쁘": "pretty",
            "아름답": "pretty",
            "귀엽": "cute",
            "활발": "lively",
            "착하": "kind",
            "친절": "kind",
            "무섭": "scary",
            "이상하": "eccentric",
            "달랐": "different",
            "다르": "different",
            "싸하": "uneasy",
            "불안": "anxious",
            "화나": "angry",
            "잘생겼": "handsome",
            "적극적": "proactive",
            "funny": "funny",
            "pretty": "pretty",
            "cute": "cute",
            "kind": "kind",
            "scary": "scary",
            "handsome": "handsome",
            "proactive": "proactive",
            "나쁘": "bad",
            "악하": "bad",
            "못되": "bad",
            "bad": "bad",
            "evil": "bad",
        }
        for alias, canonical in alias_map.items():
            if alias in key:
                return canonical
        return key

    def _trait_matches_query(
        self,
        item: dict[str, Any],
        descriptor: str,
        canonical: str,
    ) -> bool:
        trait_value = str(item.get("trait") or "")
        surface = str(item.get("surface") or "")
        trait_key = self._descriptor_key(trait_value)
        surface_key = self._descriptor_key(surface)
        query_key = self._descriptor_key(descriptor)
        canonical_key = self._descriptor_key(canonical)

        if canonical_key and canonical_key == trait_key:
            return True
        if query_key and (query_key in trait_key or query_key in surface_key):
            return True

        if trait_value.startswith("provisional:"):
            provisional_key = self._descriptor_key(trait_value.split(":", 1)[1])
            if query_key and query_key in provisional_key:
                return True
            if canonical_key and canonical_key in provisional_key:
                return True

        return False

    def _descriptor_key(self, text: str) -> str:
        compact = text.lower().strip()
        compact = re.sub(r"[^\w가-힣]+", "", compact)
        for suffix in ["사람", "캐릭터", "애", "이다", "다", "한", "는", "은", "이", "가", "야", "요"]:
            if compact.endswith(suffix) and len(compact) > len(suffix):
                compact = compact[:-len(suffix)]
        return compact

    def _extract_relationship_pair(self, query: str) -> tuple[str, str] | None:
        patterns = [
            r"(?P<a>[가-힣A-Za-z]{2,}?)(?:과|와)\s*(?P<b>[가-힣A-Za-z]{2,}?)(?:의|은|는)?\s*관계",
            r"(?P<a>[가-힣A-Za-z]{2,}?)(?:과|와)\s*(?P<b>[가-힣A-Za-z]{2,}?)(?:은|는|이|가)?\s*어떤\s*관계",
            r"relationship between (?P<a>.+?) and (?P<b>.+)$",
            r"how does (?P<a>.+?) relate to (?P<b>.+)$",
            r"what is the relationship of (?P<a>.+?) with (?P<b>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("a").strip(" ?"), match.group("b").strip(" ?")
        return None

    def _extract_status_target(self, query: str) -> str | None:
        patterns = [
            r"(?P<name>[가-힣A-Za-z]{2,}?)(?:의|은|는|이|가)?\s*(?:현재\s*)?(?:상태|상황)(?:는|은|가|이)?",
            r"(?P<name>[가-힣A-Za-z]{2,}?)(?:이|가)?\s*(?:살아있|살아 있|생존해|아직 살)",
            r"status of (?P<name>.+)$",
            r"is (?P<name>.+?) alive$",
            r"what is (?P<name>.+?)'s status$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("name").strip(" ?")
        return None

    def _extract_location_target(self, query: str) -> str | None:
        patterns = [
            r"(?P<name>[가-힣A-Za-z]{2,}?)(?:은|는|이|가)?\s*(?:어디|어느\s*곳|어느\s*장소)(?:에|에서|있|있나|있어|있나요)?",
            r"(?P<name>[가-힣A-Za-z]{2,}?)(?:의)?\s*(?:현재\s*)?위치",
            r"where is (?P<name>.+)$",
            r"where was (?P<name>.+) last seen$",
            r"what is (?P<name>.+?)'s location$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("name").strip(" ?")
        return None

    def _extract_event_target(self, query: str) -> str | None:
        patterns = [
            r"(?P<name>[가-힣A-Za-z]{2,}?)(?:에게|에게는|한테)?\s*(?:무슨|어떤)\s*일",
            r"(?P<name>[가-힣A-Za-z]{2,}?)(?:의|에 대한)?\s*사건\s*(?:요약|정리|기록)",
            r"(?P<name>[가-힣A-Za-z]{2,}?)(?:에게)?\s*일어난\s*(?:일|사건)",
            r"what happened to (?P<name>.+)$",
            r"tell me what happened to (?P<name>.+)$",
            r"summarize (?P<name>.+?)'s events$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("name").strip(" ?")
        return None

    def _extract_dimension_query(self, query: str) -> tuple[str, str | None] | None:
        lower = query.lower().strip()
        dimension_map = {
            "trust": ["who trusts", "trusted by", "trust relationships"],
            "friendship": ["who is friends with", "friendships of", "friendship relationships"],
            "hatred": ["who hates", "hatred toward", "hate relationships"],
            "alliance": ["who is allied with", "alliances of", "alliance relationships"],
        }
        for dimension, phrases in dimension_map.items():
            for phrase in phrases:
                if lower.startswith(phrase):
                    tail = query[len(phrase):].strip(" ?")
                    return dimension, tail or None

        # Korean dimension queries — anchored to start of sentence
        korean_map: list[tuple[str, list[str]]] = [
            ("trust", ["신뢰 관계", "신뢰관계", "서로 신뢰하는", "누구를 신뢰"]),
            ("alliance", ["동맹 관계", "동맹관계", "동맹을 맺은", "누구와 동맹"]),
            ("friendship", ["친구 관계", "우정 관계", "누구와 친한", "가장 친한"]),
            ("hatred", ["적대 관계", "혐오 관계", "누구를 싫어", "적으로 여기"]),
        ]
        for dimension, phrases in korean_map:
            for phrase in phrases:
                if phrase in lower:
                    return dimension, None
        return None

    def _infer_location_from_memory(self, name: str) -> dict[str, Any] | None:
        hits = self._memory_service.search_hierarchy(name, character_name=name, limit=10)
        explicit_patterns = [
            r"Location ['\"](?P<location>[^'\"]+)['\"] is established",
            r"\b(?P<name>[A-Z][a-zA-Z\- ]+)\b[^.?!]*\b(?:traveled|travelled|went|moved|arrived|returned)\b[^.?!]*\bto\b[^.?!]*\b(?:the )?(?P<location>[a-zA-Z][a-zA-Z\- ]+)\b",
        ]
        patterns = [
            r"\b(?:in|at|to|into|inside|within) the ([a-zA-Z][a-zA-Z\- ]+)\b",
            r"\b(?:in|at|to|into|inside|within) ([A-Z][a-zA-Z\- ]+)\b",
        ]
        for hit in hits:
            content = hit.content
            for pattern in explicit_patterns:
                match = re.search(pattern, content)
                if match and (location := match.groupdict().get("location")):
                    return {
                        "location": location.strip().rstrip("."),
                        "source_type": hit.source_type,
                        "content": hit.content,
                        "score": hit.score,
                    }
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return {
                        "location": match.group(1).strip().rstrip("."),
                        "source_type": hit.source_type,
                        "content": hit.content,
                        "score": hit.score,
                    }
        return None

    def _find_character(self, name: str):
        for character in self._characters.list():
            if character.name.lower() == name.lower():
                return character
        return None
