"""
Entity Extractor -- stage 1 of the mutation pipeline.

Strategy (no heavy NLP deps required):
1. Regex/heuristic pass: detect capitalised noun phrases -> character candidates;
   keyword matching for locations/objects.
2. Action extraction: verb-pattern matching -> ExtractedAction list.
3. Optional LLM refinement: structured JSON prompt; LLM wins on attributes,
   regex wins on coverage.
4. Known-entity enrichment: match extracted names against DB records to attach
   db_id and canonical_name.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.llm.providers.base import BaseLLMProvider, LLMMessage
from backend.narrative.mutation.models import (
    ACTION_PATTERNS,
    ExtractedAction,
    ExtractedEntities,
    ExtractedEntity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_PLACEHOLDER_NAMES = {"...", "…", "<name>", "<character_name>", "<location_name>",
                      "character_name", "location_name", "object_name", "concept_name", ""}

_STOPWORDS = {
    # English
    "the", "a", "an", "he", "she", "they", "it", "his", "her", "their",
    "this", "that", "these", "those", "then", "there", "when", "where",
    "what", "who", "which", "said", "asked", "replied",
    # Korean pronouns, particles, and non-name common words
    "그", "그녀", "그는", "그가", "그의", "그녀는", "그녀가", "그녀의",
    "그들", "그들은", "그들이", "그들의", "그것", "그것은", "그것이",
    "나", "나는", "나의", "내가", "내", "저", "저는", "저의", "제가",
    "너", "너는", "너의", "네가", "당신", "당신은", "당신의",
    "우리", "우리는", "우리의", "이", "저것", "이것", "것", "수많",
    "특히", "하지만", "그래서", "그리고", "또는", "또한", "그런데",
    "그렇게", "하나", "이미", "오직", "모든", "각각", "서로",
    # Korean common nouns that are not character names
    "가족", "행동", "선택", "수호", "수호자", "상황", "이유", "목적",
    "의지", "결정", "방법", "방향", "세계", "세상", "생각", "마음",
    "시간", "공간", "현실", "진실", "비밀", "운명", "전쟁", "평화",
    "자유", "정의", "희망", "죽음", "사람", "두", "세", "여러",
    "신념", "바람", "꿈", "기억", "감정", "눈물", "빛", "어둠",
    "랜턴", "선택의", "두사람", "두인물",
}

_KO_PARTICLE_SUFFIX = re.compile(
    r"(을|를|은|는|이|가|의|와|과|에|로|으로|도|만|까지|부터|에서|이야|야|랑|이랑)$"
)

_TEMPORAL_PREFIXES = {
    "after", "before", "later", "then", "next", "meanwhile", "suddenly", "moments later",
}


def _is_valid_name(name: str) -> bool:
    stripped = name.strip().strip(".")
    if not stripped or stripped in _PLACEHOLDER_NAMES or len(stripped) < 2:
        return False
    lower = stripped.lower()
    if lower in _STOPWORDS:
        return False
    # Strip Korean particles and validate the stem too
    stem = _KO_PARTICLE_SUFFIX.sub("", lower)
    if stem != lower and (stem in _STOPWORDS or len(stem) < 2):
        return False
    return True


def _normalize_entity_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name).strip(" .,!?:;\"'")
    if not normalized:
        return ""

    lower = normalized.lower()
    if lower in _TEMPORAL_PREFIXES:
        return ""

    for prefix in sorted(_TEMPORAL_PREFIXES, key=len, reverse=True):
        token = f"{prefix} "
        if lower.startswith(token):
            normalized = normalized[len(token):].strip()
            break

    lowered = normalized.lower()
    if lowered.startswith("the ") and len(normalized) > 4 and normalized[4:5].islower():
        normalized = normalized[4:].strip()
    elif lowered.startswith("an ") and len(normalized) > 3 and normalized[3:4].islower():
        normalized = normalized[3:].strip()
    elif lowered.startswith("a ") and len(normalized) > 2 and normalized[2:3].islower():
        normalized = normalized[2:].strip()

    if not normalized:
        return ""
    return normalized


# ---------------------------------------------------------------------------
# Heuristic patterns
# ---------------------------------------------------------------------------

_PROPER_NOUN_RE = re.compile(
    r"\b([A-ZÀ-ÖØ-Ý]"
    r"[a-zà-öø-ý]+"
    r"(?:\s+[A-ZÀ-ÖØ-Ý]"
    r"[a-zà-öø-ý]+)*)\b"
)

_LOCATION_KEYWORDS = {
    # 한국어 장소 키워드
    "성", "숲", "도시", "마을", "왕국", "동굴", "산", "강", "궁전", "탑",
    "폐허", "신전", "사원", "여관", "방", "홀", "거리", "다리", "항구",
    "계곡", "섬", "해안", "들판", "전장", "시장", "광장", "요새", "감옥",
    "황야", "벌판", "숲속", "해변", "바다", "호수", "골목", "광야",
    # 영어 병행 지원 (영어 소설 참고용)
    "castle", "forest", "city", "town", "village", "kingdom", "cave",
    "mountain", "river", "palace", "dungeon", "ruins", "temple", "inn",
    "tower", "room", "hall", "bridge", "port", "valley", "island",
    "field", "battlefield", "fortress",
}

_OBJECT_KEYWORDS = {
    # 한국어 물건 키워드
    "검", "방패", "반지", "두루마리", "지도", "열쇠", "책", "약", "지팡이",
    "왕관", "보석", "부적", "단검", "망토", "랜턴", "편지", "상자",
    "활", "화살", "도끼", "창", "구슬", "유물", "성물", "문서", "인장",
    "갑옷", "투구", "장갑", "망원경", "나침반", "횃불", "수정",
    # 영어 병행 지원
    "sword", "shield", "ring", "scroll", "map", "key", "book", "potion",
    "staff", "crown", "gem", "amulet", "dagger", "cloak", "lantern",
    "letter", "chest", "bow", "arrow", "axe", "spear", "relic", "artifact",
}

# Compiled action patterns: (pattern, EventType, target_required)
_COMPILED_ACTIONS = [
    (re.compile(pat, re.IGNORECASE), etype, tgt)
    for pat, etype, tgt in ACTION_PATTERNS
]

_ENTITY_EXTRACTION_PROMPT = """\
당신은 서사 엔티티 추출기입니다. 한국어 소설을 처리합니다.
아래 장면 텍스트에 등장하는 모든 엔티티를 추출하세요.
마크다운 없이 유효한 JSON 객체만 반환하세요.

JSON 구조:
{{
  "characters": [{{"name": "<인물의 고유 이름>", "attributes": {{"role": "<역할>", "emotion": "<감정>", "action": "<행동>"}}}}],
  "locations":  [{{"name": "<텍스트에 나온 정확한 장소 이름>", "attributes": {{"type": "<실내|실외|기타>"}}}}],
  "objects":    [{{"name": "<텍스트에 나온 정확한 사물 이름>", "attributes": {{"significance": "<의미>"}}}}],
  "concepts":   [{{"name": "<텍스트의 추상적 개념>", "attributes": {{}}}}]
}}

규칙:
- 장면 텍스트에 실제로 등장하는 이름만 사용하세요.
- 이 프롬프트의 예시에서 이름이나 속성을 복사하지 마세요.
- 해당 카테고리에 엔티티가 없으면 빈 배열 []을 사용하세요.
- 인물(characters)은 반드시 고유명사 — 실제 이름이어야 합니다. 대명사는 안 됩니다.
- 다음 한국어 대명사를 인물로 추출하지 마세요: 그, 그녀, 그는, 그가, 그의, 그들, 나, 저, 너, 당신, 우리.
- 한국어 부사, 조사, 접속사, 일반 명사를 인물로 추출하지 마세요.
- 대명사로만 언급되고 이름이 없는 인물은 생략하세요.

장면 텍스트:
{scene_text}"""


# ---------------------------------------------------------------------------
# EntityExtractor
# ---------------------------------------------------------------------------

class EntityExtractor:
    def __init__(
        self,
        llm_provider: BaseLLMProvider | None = None,
        character_repo: Any | None = None,
    ) -> None:
        self._llm        = llm_provider
        self._char_repo  = character_repo

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract(self, scene_text: str) -> ExtractedEntities:
        heuristic = self._heuristic_extract(scene_text)

        if self._llm is not None:
            try:
                llm_result = self._llm_extract(scene_text)
                merged = self._merge(heuristic, llm_result)
            except Exception as exc:
                logger.warning("LLM entity extraction failed, using heuristics only: %s", exc)
                merged = heuristic
        else:
            merged = heuristic

        # Action extraction (heuristic, always runs)
        merged.actions = self._extract_actions(scene_text, merged)

        # Enrich with DB known-character info
        if self._char_repo is not None:
            self._enrich_from_db(merged)

        return merged

    # ------------------------------------------------------------------
    # Heuristic entity pass
    # ------------------------------------------------------------------

    def _heuristic_extract(self, text: str) -> ExtractedEntities:
        entities = ExtractedEntities()
        seen: set[str] = set()
        existing_locations: set[str] = set()
        existing_objects: set[str] = set()

        for match in _PROPER_NOUN_RE.finditer(text):
            name = _normalize_entity_name(match.group(1))
            if name in seen or not _is_valid_name(name):
                continue
            seen.add(name)
            lower = name.lower()

            if any(kw in lower for kw in _LOCATION_KEYWORDS):
                entities.locations.append(
                    ExtractedEntity(name=name, entity_type="location", confidence=0.7))
                existing_locations.add(lower)
            elif any(kw in lower for kw in _OBJECT_KEYWORDS):
                entities.objects.append(
                    ExtractedEntity(name=name, entity_type="object", confidence=0.7))
                existing_objects.add(lower)
            else:
                entities.characters.append(
                    ExtractedEntity(name=name, entity_type="character", confidence=0.6))

        lower_text = text.lower()
        for keyword in sorted(_LOCATION_KEYWORDS):
            if keyword in existing_locations:
                continue
            if re.search(rf"\b{re.escape(keyword)}\b", lower_text):
                entities.locations.append(
                    ExtractedEntity(name=keyword, entity_type="location", confidence=0.65))
                existing_locations.add(keyword)

        for keyword in sorted(_OBJECT_KEYWORDS):
            if keyword in existing_objects:
                continue
            if re.search(rf"\b{re.escape(keyword)}\b", lower_text):
                entities.objects.append(
                    ExtractedEntity(name=keyword, entity_type="object", confidence=0.65))
                existing_objects.add(keyword)

        return entities

    # ------------------------------------------------------------------
    # Action extraction (regex verb patterns)
    # ------------------------------------------------------------------

    def _extract_actions(self, text: str, entities: ExtractedEntities) -> list[ExtractedAction]:
        char_names = {e.name.lower(): e.name for e in entities.characters}
        loc_names  = {e.name.lower(): e.name for e in entities.locations}
        sentences  = re.split(r"(?<=[.!?])\s+", text)
        actions: list[ExtractedAction] = []

        for sentence in sentences:
            for pattern, event_type, _target_req in _COMPILED_ACTIONS:
                m = pattern.search(sentence)
                if not m:
                    continue
                verb = m.group(0)
                actor, target, location = self._parse_actor_target(
                    sentence, m.start(), char_names, loc_names
                )
                if actor is None:
                    continue
                if any(a.verb.lower() == verb.lower() and a.actor == actor for a in actions):
                    continue
                actions.append(ExtractedAction(
                    verb=verb,
                    actor=actor,
                    target=target,
                    location=location,
                    event_type=event_type,
                    confidence=0.75,
                ))

        return actions

    def _parse_actor_target(
        self,
        sentence: str,
        verb_pos: int,
        char_names: dict[str, str],
        loc_names: dict[str, str],
    ) -> tuple[str | None, str | None, str | None]:
        words_before = sentence[:verb_pos].lower()
        words_after  = sentence[verb_pos:].lower()
        actor = None
        target = None
        location = None

        for lower, canonical in char_names.items():
            pos = words_before.rfind(lower)
            if pos != -1:
                actor_pos = words_before.rfind(
                    char_names.get(actor, "").lower()) if actor else -1
                if actor is None or pos > actor_pos:
                    actor = canonical

        first_target_pos = len(words_after) + 1
        for lower, canonical in char_names.items():
            pos = words_after.find(lower)
            if pos != -1 and canonical != actor:
                if pos < first_target_pos:
                    first_target_pos = pos
                    target = canonical

        for lower, canonical in loc_names.items():
            if lower in sentence.lower():
                location = canonical
                break

        return actor, target, location

    # ------------------------------------------------------------------
    # LLM pass
    # ------------------------------------------------------------------

    def _llm_extract(self, scene_text: str) -> ExtractedEntities:
        prompt = _ENTITY_EXTRACTION_PROMPT.format(scene_text=scene_text)
        response = self._llm.complete([
            LLMMessage(role="system",
                       content="당신은 한국어 소설 전문 서사 엔티티 추출기입니다. 유효한 JSON만 반환하세요."),
            LLMMessage(role="user", content=prompt),
        ])
        return self._parse_llm_response(response.content)

    def _parse_llm_response(self, raw: str) -> ExtractedEntities:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
        try:
            data: dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not m:
                raise ValueError(f"Cannot parse LLM response as JSON: {raw[:200]}")
            data = json.loads(m.group())

        result = ExtractedEntities()
        for item in data.get("characters", []):
            name = _normalize_entity_name(item.get("name", ""))
            if _is_valid_name(name):
                result.characters.append(ExtractedEntity(
                    name=name, entity_type="character",
                    attributes=item.get("attributes", {}), confidence=0.9))
        for item in data.get("locations", []):
            name = _normalize_entity_name(item.get("name", ""))
            if _is_valid_name(name):
                result.locations.append(ExtractedEntity(
                    name=name, entity_type="location",
                    attributes=item.get("attributes", {}), confidence=0.9))
        for item in data.get("objects", []):
            name = _normalize_entity_name(item.get("name", ""))
            if _is_valid_name(name):
                result.objects.append(ExtractedEntity(
                    name=name, entity_type="object",
                    attributes=item.get("attributes", {}), confidence=0.9))
        for item in data.get("concepts", []):
            name = _normalize_entity_name(item.get("name", ""))
            if _is_valid_name(name):
                result.concepts.append(ExtractedEntity(
                    name=name, entity_type="concept",
                    attributes=item.get("attributes", {}), confidence=0.85))
        return result

    # ------------------------------------------------------------------
    # Merge heuristic + LLM
    # ------------------------------------------------------------------

    def _merge(self, heuristic: ExtractedEntities, llm: ExtractedEntities) -> ExtractedEntities:
        merged = ExtractedEntities()

        def _merge_list(h_list: list, l_list: list) -> list:
            by_name: dict[str, ExtractedEntity] = {e.name.lower(): e for e in h_list}
            for llm_e in l_list:
                key = llm_e.name.lower()
                if key in by_name:
                    by_name[key].attributes.update(llm_e.attributes)
                    by_name[key].confidence = max(by_name[key].confidence, llm_e.confidence)
                else:
                    by_name[key] = llm_e
            return list(by_name.values())

        merged.characters = _merge_list(heuristic.characters, llm.characters)
        merged.locations  = _merge_list(heuristic.locations,  llm.locations)
        merged.objects    = _merge_list(heuristic.objects,    llm.objects)
        merged.concepts   = _merge_list(heuristic.concepts,   llm.concepts)
        return merged

    # ------------------------------------------------------------------
    # DB enrichment: match names to known DB records
    # ------------------------------------------------------------------

    def _enrich_from_db(self, entities: ExtractedEntities) -> None:
        try:
            all_chars = self._char_repo.list()
        except Exception as exc:
            logger.warning("DB enrichment failed: %s", exc)
            return

        db_by_lower = {c.name.lower(): c for c in all_chars}
        for entity in entities.characters:
            lower = entity.name.lower()
            if lower in db_by_lower:
                db_char = db_by_lower[lower]
                entity.db_id = db_char.id
                entity.canonical_name = db_char.name
                entity.confidence = min(1.0, entity.confidence + 0.2)
