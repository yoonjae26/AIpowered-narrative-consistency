"""
Event Generator -- stage 2 of the mutation pipeline.

Takes ExtractedEntities (including actions) + scene_text -> list[NarrativeEvent].

Priority:
  1. Action-derived events: each ExtractedAction -> structured NarrativeEvent
  2. LLM generation (if provider available)
  3. Heuristic fallback: CHARACTER_APPEARS per character, WORLD_STATE_CHANGE per location
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, UTC
from typing import Any
from backend.llm.providers.base import BaseLLMProvider, LLMMessage
from backend.narrative.mutation.models import EventType, ExtractedEntities, NarrativeEvent
from backend.narrative.semantic_relation_extractor import KoreanSemanticRelationExtractor

logger = logging.getLogger(__name__)

# Human-readable predicate templates per event type (Korean)
_PREDICATES: dict[EventType, str] = {
    EventType.MURDER:              "{subject}이(가) {target}을(를) 살해함",
    EventType.DEATH:               "{subject}이(가) 사망함",
    EventType.INJURY:              "{subject}이(가) {target}에게 부상을 입힘",
    EventType.BIRTH:               "{subject}이(가) 태어남",
    EventType.RESURRECTION:        "{subject}이(가) 부활함",
    EventType.MARRIAGE:            "{subject}이(가) {target}과(와) 혼인함",
    EventType.BETRAYAL:            "{subject}이(가) {target}을(를) 배신함",
    EventType.ALLIANCE:            "{subject}이(가) {target}과(와) 동맹을 맺음",
    EventType.CONFLICT:            "{subject}이(가) {target}과(와) 충돌함",
    EventType.DISCOVERY:           "{subject}이(가) 무언가를 발견함",
    EventType.TRAVEL:              "{subject}이(가) 이동함",
    EventType.CAPTURE:             "{subject}이(가) {target}을(를) 포획함",
    EventType.ESCAPE:              "{subject}이(가) 탈출함",
    EventType.CHARACTER_APPEARS:   "{subject}이(가) 장면에 등장함",
    EventType.CHARACTER_EXITS:     "{subject}이(가) 장면에서 퇴장함",
    EventType.CHARACTER_CHANGES:   "{subject}에게 변화가 일어남",
    EventType.RELATIONSHIP_FORMS:  "{subject}과(와) {target} 사이에 관계가 형성됨",
    EventType.RELATIONSHIP_CHANGES:"{subject}과(와) {target}의 관계가 변화함",
    EventType.SCENE_OPENS:         "장면 '{subject}' 시작",
    EventType.SCENE_CLOSES:        "장면 '{subject}' 종료",
    EventType.TIMELINE_BEAT:       "장면 사건이 타임라인에 기록됨",
    EventType.WORLD_STATE_CHANGE:  "'{subject}' 공간이 설정됨",
}

_EVENT_GENERATION_PROMPT = """당신은 스토리 엔진을 위한 서사 사건 추출기입니다.
장면 텍스트와 이미 추출된 등장인물 정보를 바탕으로 서사 사건의 JSON 배열을 생성하세요.

각 사건 객체는 반드시 다음 필드를 포함해야 합니다:
  "event_type": {event_types} 중 하나
  "subject":    주체 인물 이름 (문자열)
  "predicate":  발생한 사건에 대한 간결한 설명 (문자열, 최대 20어절)
  "target":     대상 인물 이름 또는 null
  "action":     원형 동사 (예: "살해", "혼인") 또는 null
  "location":   장소 이름 또는 null
  "attributes": 추가 사실 딕셔너리

마크다운 없이 JSON 배열만 반환하세요.

등장인물: {entities_summary}

장면 텍스트:
{scene_text}"""


class EventGenerator:
    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self._llm = llm_provider
        self._semantic_extractor = KoreanSemanticRelationExtractor()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(self, scene_text: str, entities: ExtractedEntities,
                 scene_title: str | None = None) -> list[NarrativeEvent]:
        now = datetime.now(UTC)
        events: list[NarrativeEvent] = []

        # Always open the scene
        if scene_title:
            events.append(NarrativeEvent(
                event_type=EventType.SCENE_OPENS,
                subject=scene_title,
                predicate=f"장면 '{scene_title}' 시작",
                source_scene=scene_title,
                timestamp=now,
            ))

        # 1. Action-derived events (highest fidelity)
        action_events = self._events_from_actions(entities, scene_title, now)
        events.extend(action_events)
        covered_subjects = {e.subject.lower() for e in action_events}

        semantic_events = self._events_from_semantics(scene_text, entities, scene_title, now)
        events.extend(semantic_events)
        covered_subjects.update(e.subject.lower() for e in semantic_events)

        # 2. LLM events (if no actions found or LLM available)
        if self._llm is not None and not action_events:
            try:
                llm_events = self._llm_generate(scene_text, entities, scene_title)
                events.extend(llm_events)
                covered_subjects.update(e.subject.lower() for e in llm_events)
            except Exception as exc:
                logger.warning("LLM event generation failed, using heuristics: %s", exc)

        # 3. Heuristic: ensure every character/location has at least one event
        for char in entities.characters:
            if char.name.lower() not in covered_subjects:
                events.append(NarrativeEvent(
                    event_type=EventType.CHARACTER_APPEARS,
                    subject=char.name,
                    predicate=f"{char.name}이(가) 장면에 등장함",
                    attributes=char.attributes,
                    source_scene=scene_title,
                    timestamp=now,
                ))

        for loc in entities.locations:
            events.append(NarrativeEvent(
                event_type=EventType.WORLD_STATE_CHANGE,
                subject=loc.name,
                predicate=f"'{loc.name}' 공간이 설정됨",
                attributes=loc.attributes,
                source_scene=scene_title,
                timestamp=now,
            ))

        # Always close with a timeline beat
        events.append(NarrativeEvent(
            event_type=EventType.TIMELINE_BEAT,
            subject=scene_title or "Scene",
            predicate="장면 사건이 타임라인에 기록됨",
            source_scene=scene_title,
            timestamp=now,
        ))

        return events

    def _events_from_semantics(
        self,
        scene_text: str,
        entities: ExtractedEntities,
        scene_title: str | None,
        now: datetime,
    ) -> list[NarrativeEvent]:
        known_names = [entity.name for entity in entities.characters]
        relations = self._semantic_extractor.extract(scene_text, known_character_names=known_names)

        events: list[NarrativeEvent] = []
        for relation in relations:
            is_emotion = relation.relation == "has_emotion"
            etype = EventType.CHAR_EMOTION if is_emotion else EventType.CHAR_TRAIT
            if is_emotion:
                predicate = f"{relation.subject}이(가) {relation.value}을(를) 느낌"
                attributes = {
                    "relation_type": relation.relation,
                    "emotion": relation.value,
                    "surface_descriptor": relation.surface,
                    "semantic_confidence": relation.confidence,
                    "confidence": relation.confidence,
                    "provisional": relation.provisional,
                }
            else:
                predicate = f"{relation.subject}의 특성: {relation.value}"
                attributes = {
                    "relation_type": relation.relation,
                    "trait": relation.value,
                    "surface_descriptor": relation.surface,
                    "semantic_confidence": relation.confidence,
                    "confidence": relation.confidence,
                    "provisional": relation.provisional,
                }

            events.append(
                NarrativeEvent(
                    event_type=etype,
                    subject=relation.subject,
                    predicate=predicate,
                    target=relation.value,
                    action=relation.relation,
                    attributes=attributes,
                    source_scene=scene_title,
                    timestamp=now,
                )
            )
        return events

    # ------------------------------------------------------------------
    # Action -> NarrativeEvent conversion
    # ------------------------------------------------------------------

    def _events_from_actions(
        self,
        entities: ExtractedEntities,
        scene_title: str | None,
        now: datetime,
    ) -> list[NarrativeEvent]:
        events: list[NarrativeEvent] = []
        for action in entities.actions:
            template = _PREDICATES.get(action.event_type, "{subject} {verb} {target}")
            predicate = (template
                         .replace("{subject}", action.actor)
                         .replace("{target}", action.target or "")
                         .replace("{verb}", action.verb)
                         .strip())

            events.append(NarrativeEvent(
                event_type=action.event_type,
                subject=action.actor,
                predicate=predicate,
                target=action.target,
                action=action.verb,
                location=action.location,
                attributes={"verb": action.verb, "confidence": action.confidence},
                source_scene=scene_title,
                timestamp=now,
            ))
        return events

    # ------------------------------------------------------------------
    # LLM generation
    # ------------------------------------------------------------------

    def _llm_generate(self, scene_text: str, entities: ExtractedEntities,
                      scene_title: str | None) -> list[NarrativeEvent]:
        event_types_str = ", ".join(e.value for e in EventType)
        entities_summary = self._summarise_entities(entities)

        prompt = _EVENT_GENERATION_PROMPT.format(
            event_types=event_types_str,
            entities_summary=entities_summary,
            scene_text=scene_text,
        )
        response = self._llm.complete([
            LLMMessage(role="system",
                       content="당신은 정밀한 서사 사건 추출기입니다. 유효한 JSON 배열만 반환하세요."),
            LLMMessage(role="user", content=prompt),
        ])
        return self._parse_llm_response(response.content, scene_title)

    def _summarise_entities(self, entities: ExtractedEntities) -> str:
        parts: list[str] = []
        if entities.characters:
            parts.append("characters: " + ", ".join(e.name for e in entities.characters))
        if entities.locations:
            parts.append("locations: " + ", ".join(e.name for e in entities.locations))
        if entities.objects:
            parts.append("objects: " + ", ".join(e.name for e in entities.objects))
        if entities.actions:
            parts.append("actions: " + ", ".join(
                f"{a.actor} {a.verb}" + (f" {a.target}" if a.target else "")
                for a in entities.actions
            ))
        return "; ".join(parts) or "none"

    def _parse_llm_response(self, raw: str, scene_title: str | None) -> list[NarrativeEvent]:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
        try:
            items: list[dict] = json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if not m:
                raise ValueError(f"Cannot parse LLM events: {raw[:200]}")
            items = json.loads(m.group())

        events: list[NarrativeEvent] = []
        now = datetime.now(UTC)
        for item in items:
            try:
                etype = EventType(item["event_type"])
            except (KeyError, ValueError):
                continue
            events.append(NarrativeEvent(
                event_type=etype,
                subject=item.get("subject", "Unknown"),
                predicate=item.get("predicate", ""),
                target=item.get("target"),
                action=item.get("action"),
                location=item.get("location"),
                attributes=item.get("attributes", {}),
                source_scene=scene_title,
                timestamp=now,
            ))
        return events
