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
from datetime import datetime
from typing import Any

from backend.llm.providers.base import BaseLLMProvider, LLMMessage
from backend.narrative.mutation.models import EventType, ExtractedEntities, NarrativeEvent

logger = logging.getLogger(__name__)

# Human-readable predicate templates per event type
_PREDICATES: dict[EventType, str] = {
    EventType.MURDER:              "{subject} kills {target}",
    EventType.DEATH:               "{subject} dies",
    EventType.INJURY:              "{subject} injures {target}",
    EventType.BIRTH:               "{subject} is born",
    EventType.RESURRECTION:        "{subject} is resurrected",
    EventType.MARRIAGE:            "{subject} marries {target}",
    EventType.BETRAYAL:            "{subject} betrays {target}",
    EventType.ALLIANCE:            "{subject} forms alliance with {target}",
    EventType.CONFLICT:            "{subject} clashes with {target}",
    EventType.DISCOVERY:           "{subject} discovers something",
    EventType.TRAVEL:              "{subject} travels",
    EventType.CAPTURE:             "{subject} captures {target}",
    EventType.ESCAPE:              "{subject} escapes",
    EventType.CHARACTER_APPEARS:   "{subject} appears in the scene",
    EventType.CHARACTER_EXITS:     "{subject} exits the scene",
    EventType.CHARACTER_CHANGES:   "{subject} undergoes a change",
    EventType.RELATIONSHIP_FORMS:  "{subject} and {target} form a relationship",
    EventType.RELATIONSHIP_CHANGES:"{subject} and {target} relationship changes",
    EventType.SCENE_OPENS:         "Scene '{subject}' begins",
    EventType.SCENE_CLOSES:        "Scene '{subject}' ends",
    EventType.TIMELINE_BEAT:       "Scene events recorded on timeline",
    EventType.WORLD_STATE_CHANGE:  "Location '{subject}' is established",
}

_EVENT_GENERATION_PROMPT = """You are a narrative event extractor for a story engine.
Given the scene text and the entities already extracted, produce a JSON array of narrative events.

Each event object must have:
  "event_type": one of {event_types}
  "subject":    primary entity name (string)
  "predicate":  concise description of what happened (string, max 20 words)
  "target":     secondary entity name or null
  "action":     the raw verb (e.g. "killed", "married") or null
  "location":   location name or null
  "attributes": dict of extra facts

Return ONLY the JSON array, no markdown, no extra text.

Entities: {entities_summary}

Scene text:
{scene_text}"""


class EventGenerator:
    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self._llm = llm_provider

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(self, scene_text: str, entities: ExtractedEntities,
                 scene_title: str | None = None) -> list[NarrativeEvent]:
        now = datetime.utcnow()
        events: list[NarrativeEvent] = []

        # Always open the scene
        if scene_title:
            events.append(NarrativeEvent(
                event_type=EventType.SCENE_OPENS,
                subject=scene_title,
                predicate=f"Scene '{scene_title}' begins",
                source_scene=scene_title,
                timestamp=now,
            ))

        # 1. Action-derived events (highest fidelity)
        action_events = self._events_from_actions(entities, scene_title, now)
        events.extend(action_events)
        covered_subjects = {e.subject.lower() for e in action_events}

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
                    predicate=f"{char.name} appears in the scene",
                    attributes=char.attributes,
                    source_scene=scene_title,
                    timestamp=now,
                ))

        for loc in entities.locations:
            events.append(NarrativeEvent(
                event_type=EventType.WORLD_STATE_CHANGE,
                subject=loc.name,
                predicate=f"Location '{loc.name}' is established",
                attributes=loc.attributes,
                source_scene=scene_title,
                timestamp=now,
            ))

        # Always close with a timeline beat
        events.append(NarrativeEvent(
            event_type=EventType.TIMELINE_BEAT,
            subject=scene_title or "Scene",
            predicate="Scene events recorded on timeline",
            source_scene=scene_title,
            timestamp=now,
        ))

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
                       content="You are a precise narrative event extractor. Return only valid JSON arrays."),
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
        now = datetime.utcnow()
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
