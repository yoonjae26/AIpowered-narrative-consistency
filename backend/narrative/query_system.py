from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.narrative.character.memory_system import CharacterMemorySystem
from backend.narrative.korean_text import extract_character_query_name, normalize_korean_text
from backend.narrative.relationships.graph import RelationshipGraph
from backend.rag import NarrativeMemoryService
from backend.version_control.event_store import EventStore


@dataclass(slots=True)
class QueryAnswer:
    query: str
    answer: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


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

    def query(self, query_text: str) -> QueryAnswer:
        q = query_text.strip()
        if trait_check := self._extract_character_trait_confirmation_query(q):
            return self.confirm_character_trait(trait_check[0], trait_check[1])
        if descriptor := self._extract_trait_who_query(q):
            return self.who_has_trait(descriptor)
        if name := extract_character_query_name(q):
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
                answer="No character currently matches that descriptor in memory.",
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
            return QueryAnswer(query=f"is {name} {descriptor}", answer="Character not found.")

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
                answer=f"Yes, {character.name} is described as {descriptor}.",
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
                answer=f"Partially. There is pending evidence that {character.name} may be {descriptor}, but confidence is not high enough yet.",
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
            answer=f"No strong evidence yet that {character.name} is {descriptor}.",
            evidence=[],
        )

    def character_profile(self, name: str) -> QueryAnswer:
        character = self._find_character(name)
        if character is None:
            return QueryAnswer(query=f"character profile of {name}", answer="Character not found.")

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
            summary_bits.append("No strong internal profile signals yet.")

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
        return QueryAnswer(query=f"Who knows about {topic}?", answer="No explicit knowledge found.", evidence=[])

    def relationship_between(self, source: str, target: str) -> QueryAnswer:
        edge = self._graph.relationship_between(source, target)
        if edge is None:
            return QueryAnswer(query=f"relationship between {source} and {target}", answer="No direct relationship found.")
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
                    answer=f"{character.name} is {character.status}",
                    evidence=[{"status": character.status, "metadata": metadata}],
                )
        return QueryAnswer(query=f"status of {name}", answer="Character not found.")

    def semantic_query(self, query_text: str) -> QueryAnswer:
        routed_name = extract_character_query_name(query_text)
        normalized_query = normalize_korean_text(query_text)

        hits = self._memory_service.search_hierarchy(
            normalized_query,
            character_name=routed_name,
            limit=6
        )

        # lọc noise bằng threshold
        filtered_hits = [h for h in hits if h.score >= 0.75]

        if not filtered_hits:
            replay = self._event_store.replay_state()
            return QueryAnswer(
                query=query_text,
                answer="No relevant semantic memory found.",
                evidence=[replay]
            )

        # chọn best hit nhưng KHÔNG return raw content
        best = filtered_hits[0]

        return QueryAnswer(
            query=query_text,
            answer=best.content,   # tạm thời giữ, nhưng đã có filter
            evidence=[
                {
                    "id": hit.id,
                    "source_type": hit.source_type,
                    "score": hit.score,
                    "content": hit.content,
                }
                for hit in filtered_hits
            ],
        )

    def where_is(self, name: str) -> QueryAnswer:
        replay = self._event_store.replay_state()
        characters = replay.get("characters", {})
        if name in characters:
            location = characters[name].get("last_location")
            if location:
                return QueryAnswer(query=f"where is {name}", answer=f"{name} is at {location}.", evidence=[characters[name]])
            inferred = self._infer_location_from_memory(name)
            if inferred is not None:
                return QueryAnswer(
                    query=f"where is {name}",
                    answer=f"Best semantic match places {name} at {inferred['location']}.",
                    evidence=[characters[name], inferred],
                )
            return QueryAnswer(query=f"where is {name}", answer=f"No known location for {name}.", evidence=[characters[name]])
        return QueryAnswer(query=f"where is {name}", answer="Character not found.")

    def what_happened_to(self, name: str) -> QueryAnswer:
        events = [event for event in self._event_store.list_events() if event.subject.lower() == name.lower() or (event.target or "").lower() == name.lower()]
        if not events:
            return QueryAnswer(
                query=f"what happened to {name}",
                answer="No event history found.",
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
            return QueryAnswer(query=f"{dimension} query", answer=f"No relationships found for dimension '{dimension}'.")
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
