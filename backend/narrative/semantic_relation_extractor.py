from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


_KOREAN_CHAR_RE = re.compile(r"[가-힣]")
_SUBJECT_PARTICLE_RE = re.compile(r"^(?P<name>[가-힣A-Za-z0-9_]{2,}?)(?:은|는|이|가|도|와|과)?$")
_REVERSED_NP_RE = re.compile(r"(?P<descriptor>[가-힣\s]+?)\s*(?:사람인|인)\s*(?P<name>[가-힣A-Za-z0-9_]{2,})")
_NON_KOREAN_RE = re.compile(r"[^가-힣A-Za-z0-9_]+")

_DESCRIPTOR_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"예쁘|예쁜|아름답|매력적"), "has_trait", "pretty"),
    (re.compile(r"재밌|재미있|웃기"), "has_trait", "funny"),
    (re.compile(r"귀엽"), "has_trait", "cute"),
    (re.compile(r"활발"), "has_trait", "lively"),
    (re.compile(r"잘\s*생겼|잘생겼|훈훈"), "has_trait", "handsome"),
    (re.compile(r"적극적"), "has_trait", "proactive"),
    (re.compile(r"나쁘|악하|못되"), "has_trait", "bad"),
    (re.compile(r"이상하|이상한"), "has_trait", "eccentric"),
    (re.compile(r"달랐|다르"), "has_trait", "different"),
    (re.compile(r"싸하|싸늘"), "has_emotion", "uneasy"),
    (re.compile(r"착하|착한|친절"), "has_trait", "kind"),
    (re.compile(r"무섭"), "has_trait", "scary"),
    (re.compile(r"차갑|냉정"), "has_trait", "cold"),
    (re.compile(r"화나|분노|격노"), "has_emotion", "angry"),
    (re.compile(r"슬프|우울"), "has_emotion", "sad"),
    (re.compile(r"기쁘|행복"), "has_emotion", "happy"),
    (re.compile(r"불안|초조"), "has_emotion", "anxious"),
]


@dataclass(slots=True)
class SemanticRelation:
    subject: str
    relation: str
    value: str
    surface: str
    confidence: float
    provisional: bool = False


class KoreanSemanticRelationExtractor:
    """Extract colloquial Korean character descriptor relations.

    Output is canonicalized semantic relations such as:
    subject -> has_trait -> pretty
    subject -> has_emotion -> angry
    """

    def __init__(self, synonym_cache_path: Path | None = None) -> None:
        self._synonym_cache_path = synonym_cache_path or Path(".cache/semantic_descriptor_synonyms.json")
        self._dynamic_synonyms: dict[str, dict[str, str]] = {}
        self._load_synonyms()
        self._kiwi = None
        try:
            from kiwipiepy import Kiwi  # type: ignore
            self._kiwi = Kiwi()
        except Exception:
            self._kiwi = None

    def extract(self, text: str, known_character_names: list[str] | None = None) -> list[SemanticRelation]:
        if not text or _KOREAN_CHAR_RE.search(text) is None:
            return []

        relations: list[SemanticRelation] = []
        known_names = [name for name in (known_character_names or []) if name]

        for sentence in self._split_sentences(text):
            subject = self._extract_subject(sentence, known_names)
            if not subject:
                continue
            descriptor_candidates = self._extract_descriptor_candidates(sentence, subject)
            if not descriptor_candidates:
                continue
            relations.extend(self._extract_descriptor_relations(subject, descriptor_candidates))

        return self._dedupe(relations)

    def _split_sentences(self, text: str) -> list[str]:
        parts = re.split(r"[\n.!?]+", text)
        return [part.strip() for part in parts if part and part.strip()]

    def _extract_subject(self, sentence: str, known_names: list[str]) -> str | None:
        for name in known_names:
            if name and name in sentence:
                return name

        reverse_match = _REVERSED_NP_RE.search(sentence)
        if reverse_match:
            return reverse_match.group("name")

        tokens = sentence.split()
        if not tokens:
            return None
        first = self._clean_subject_token(tokens[0])
        particle_match = _SUBJECT_PARTICLE_RE.match(first)
        if particle_match:
            return particle_match.group("name")

        if _KOREAN_CHAR_RE.search(first) is not None and len(first) >= 2:
            return re.sub(r"(은|는|이|가|도|와|과)$", "", first)
        return None

    def _clean_subject_token(self, token: str) -> str:
        cleaned = token.strip().strip("'\".,!?;:()[]{}")
        return cleaned

    def _extract_descriptor_candidates(self, sentence: str, subject: str) -> list[str]:
        source = sentence.replace(subject, " ", 1).strip()
        source = re.sub(r"^(은|는|이|가)\s*", "", source)
        source = re.sub(r"(사람이야|사람이다|사람|애야|애|이다|야)$", "", source).strip()
        if self._kiwi is None:
            return [source] if source else []
        try:
            tokens = self._kiwi.tokenize(sentence)
            adjective_like = [tok.form for tok in tokens if str(tok.tag).startswith("VA") or str(tok.tag).startswith("XR")]
            verb_like = [tok.form for tok in tokens if str(tok.tag).startswith("VV")]
            candidates = adjective_like + verb_like
            if source:
                candidates.append(source)
            deduped: list[str] = []
            seen: set[str] = set()
            for item in candidates:
                compact = item.strip()
                if not compact or compact in seen:
                    continue
                seen.add(compact)
                deduped.append(compact)
            return deduped
        except Exception:
            return [source] if source else []

    def _extract_descriptor_relations(self, subject: str, descriptor_candidates: list[str]) -> list[SemanticRelation]:
        hits: list[SemanticRelation] = []
        base_conf = 0.82 if self._kiwi is not None else 0.64
        found_known = False

        for candidate in descriptor_candidates:
            normalized = candidate.strip()
            if not normalized:
                continue
            if re.search(r"(이다|야|다)$", normalized):
                base_conf = min(0.95, base_conf + 0.04)

            mapped = self._lookup_dynamic_synonym(normalized)
            if mapped is not None:
                hits.append(
                    SemanticRelation(
                        subject=subject,
                        relation=mapped["relation"],
                        value=mapped["canonical"],
                        surface=normalized,
                        confidence=0.76,
                    )
                )
                found_known = True
                continue

            for pattern, relation, canonical in _DESCRIPTOR_PATTERNS:
                match = pattern.search(normalized)
                if not match:
                    continue
                surface = match.group(0)
                hits.append(
                    SemanticRelation(
                        subject=subject,
                        relation=relation,
                        value=canonical,
                        surface=surface,
                        confidence=min(0.95, base_conf),
                    )
                )
                self._record_dynamic_synonym(surface, relation, canonical)
                found_known = True

        if not found_known:
            fallback_surface = self._fallback_descriptor_surface(descriptor_candidates)
            if fallback_surface:
                hits.append(
                    SemanticRelation(
                        subject=subject,
                        relation="has_trait",
                        value=f"provisional:{fallback_surface}",
                        surface=fallback_surface,
                        confidence=0.46 if self._kiwi is not None else 0.38,
                        provisional=True,
                    )
                )
        return hits

    def _fallback_descriptor_surface(self, descriptor_candidates: list[str]) -> str:
        for item in descriptor_candidates:
            compact = _NON_KOREAN_RE.sub("", item)
            compact = re.sub(r"(하다|했다|하였다|한|했던|다)$", "", compact)
            compact = compact.strip()
            if len(compact) >= 2:
                return compact
        return ""

    def _load_synonyms(self) -> None:
        if not self._synonym_cache_path.exists():
            return
        try:
            raw = json.loads(self._synonym_cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._dynamic_synonyms = {
                    str(key): {
                        "relation": str(value.get("relation") or "has_trait"),
                        "canonical": str(value.get("canonical") or ""),
                    }
                    for key, value in raw.items()
                    if isinstance(value, dict) and value.get("canonical")
                }
        except Exception:
            self._dynamic_synonyms = {}

    def _save_synonyms(self) -> None:
        self._synonym_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._synonym_cache_path.write_text(
            json.dumps(self._dynamic_synonyms, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _lookup_dynamic_synonym(self, surface: str) -> dict[str, str] | None:
        key = _NON_KOREAN_RE.sub("", surface).lower()
        if not key:
            return None
        return self._dynamic_synonyms.get(key)

    def _record_dynamic_synonym(self, surface: str, relation: str, canonical: str) -> None:
        key = _NON_KOREAN_RE.sub("", surface).lower()
        if not key or key in self._dynamic_synonyms:
            return
        self._dynamic_synonyms[key] = {
            "relation": relation,
            "canonical": canonical,
        }
        self._save_synonyms()

    def _dedupe(self, relations: list[SemanticRelation]) -> list[SemanticRelation]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[SemanticRelation] = []
        for item in relations:
            key = (item.subject.lower(), item.relation, item.value)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped