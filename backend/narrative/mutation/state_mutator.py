"""
State Mutator -- stage 3+4 of the pipeline.

Applies NarrativeEvents to persistent state via repositories.

Dispatch:
  MURDER / DEATH      -> character.status = "dead"
  INJURY              -> character.status = "injured"
  RESURRECTION        -> character.status = "alive"
  CHARACTER_APPEARS   -> upsert character, status = "alive"
  CHARACTER_EXITS     -> character.status = "absent"
  CHARACTER_CHANGES   -> update character attributes
  MARRIAGE/ALLIANCE/BETRAYAL/CONFLICT -> upsert relationship
  RELATIONSHIP_FORMS/_CHANGES         -> upsert relationship
  TRAVEL              -> update character last_location
  SCENE_OPENS/CLOSES/TIMELINE_BEAT/WORLD_STATE_CHANGE/DISCOVERY/CAPTURE/ESCAPE/BIRTH
                      -> create timeline event
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.relationship_repository import RelationshipRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.database.repositories.timeline_repository import TimelineRepository
from backend.narrative.mutation.models import (
    CharacterStatus,
    EventType,
    MutationResult,
    NarrativeEvent,
)

logger = logging.getLogger(__name__)

_NOISE_BEAT_RE = re.compile(
    r"^Scene '[^']+' begins$"
    r"|^Scene events recorded on timeline$"
    r"|^Location '[^']+' is established$"
    r"|^장면 '.+' 시작$"
    r"|^장면 사건이 타임라인에 기록됨$"
    r"|^'.+' 공간이 설정됨$"
)

def _is_story_beat(predicate: str) -> bool:
    """Return True only for actual story content, not internal pipeline metadata."""
    return "provisional:" not in predicate and not _NOISE_BEAT_RE.match(predicate)


_KOREAN_NON_NAMES = {
    "그", "그녀", "그는", "그가", "그의", "그녀는", "그녀가", "그녀의",
    "그들", "그들은", "그들이", "그들의", "그것", "그것은", "그것이",
    "나", "나는", "나의", "내가", "내", "저", "저는", "저의", "제가",
    "너", "너는", "너의", "네가", "당신", "당신은", "당신의",
    "우리", "우리는", "우리의", "이", "저것", "이것", "것", "수많",
    "특히", "하지만", "그래서", "그리고", "또는", "또한", "그런데",
    "그렇게", "하나", "이미", "오직", "모든", "각각", "서로",
}


_KOREAN_POSSESSIVE = "의"
_KOREAN_ROLE_SUFFIXES = {"부하", "부관", "병사", "신하", "기사", "경비", "경호원", "수하", "졸개", "수하인"}


def _is_valid_character_name(name: str) -> bool:
    stripped = name.strip()
    if not stripped or len(stripped) < 2:
        return False
    if stripped.lower() in _KOREAN_NON_NAMES:
        return False
    # "X의 Y" pattern (X's Y) = description not a name, unless Y is a known proper noun marker
    if _KOREAN_POSSESSIVE in stripped:
        last_token = stripped.split(_KOREAN_POSSESSIVE)[-1].strip()
        if last_token in _KOREAN_ROLE_SUFFIXES or not last_token:
            return False
    return True


# Events that change character vital status
_VITAL_STATUS_MAP: dict[EventType, str] = {
    EventType.DEATH:         CharacterStatus.DEAD.value,
    EventType.MURDER:        CharacterStatus.DEAD.value,   # target dies
    EventType.INJURY:        CharacterStatus.INJURED.value,
    EventType.RESURRECTION:  CharacterStatus.ALIVE.value,
    EventType.CHARACTER_APPEARS: CharacterStatus.ALIVE.value,
}

# Events that represent social relationships
_RELATIONSHIP_EVENTS = {
    EventType.RELATIONSHIP_FORMS,
    EventType.RELATIONSHIP_CHANGES,
    EventType.MARRIAGE,
    EventType.ALLIANCE,
    EventType.BETRAYAL,
    EventType.CONFLICT,
}

# Events that go on the timeline
_TIMELINE_EVENTS = {
    EventType.SCENE_OPENS, EventType.SCENE_CLOSES, EventType.TIMELINE_BEAT,
    EventType.WORLD_STATE_CHANGE, EventType.DISCOVERY, EventType.CAPTURE,
    EventType.ESCAPE, EventType.BIRTH, EventType.TRAVEL,
    EventType.MURDER, EventType.DEATH, EventType.INJURY,
    EventType.RESURRECTION, EventType.MARRIAGE, EventType.BETRAYAL,
    EventType.ALLIANCE, EventType.CONFLICT,
}


class StateMutator:
    def __init__(
        self,
        character_repo: CharacterRepository,
        scene_repo: SceneRepository,
        timeline_repo: TimelineRepository,
        relationship_repo: RelationshipRepository,
    ) -> None:
        self._characters    = character_repo
        self._scenes        = scene_repo
        self._timeline      = timeline_repo
        self._relationships = relationship_repo

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def apply(self, events: list[NarrativeEvent], scene_title: str | None = None, scene_text: str | None = None) -> MutationResult:
        result = MutationResult(
            scene_id=None,
            events_applied=[],
            characters_upserted=[],
            timeline_events_created=[],
            consistency_warnings=[],
        )
        char_names_in_scene: list[str] = []

        for event in events:
            try:
                self._apply_one(event, result, char_names_in_scene)
                result.events_applied.append(event)
            except Exception as exc:
                logger.error("Failed to apply event %s: %s", event.event_type, exc)
                result.consistency_warnings.append(
                    f"Could not apply event '{event.event_type.value}' for '{event.subject}': {exc}")

        # Persist the scene row when we have characters
        if scene_title and char_names_in_scene:
            try:
                scene = self._scenes.get_or_create(
                    title=scene_title,
                    summary=scene_text or None,
                    beats=[e.predicate for e in events if e.source_scene == scene_title and _is_story_beat(e.predicate)],
                    characters=char_names_in_scene,
                )
                result.scene_id = scene.id
            except Exception as exc:
                logger.warning("Scene persistence failed: %s", exc)
                result.consistency_warnings.append(f"Scene persistence failed: {exc}")

        return result

    # ------------------------------------------------------------------
    # Per-event dispatch
    # ------------------------------------------------------------------

    def _apply_one(
        self,
        event: NarrativeEvent,
        result: MutationResult,
        char_names_in_scene: list[str],
    ) -> None:
        etype = event.event_type

        # --- Vital status changes ---
        if etype in (EventType.CHARACTER_APPEARS, EventType.RESURRECTION):
            status = _VITAL_STATUS_MAP[etype]
            char_id = self._upsert_character(event.subject, event.attributes, status=status,
                                             location=event.location)
            self._record_character_upsert(result, char_id, event.subject)
            char_names_in_scene.append(event.subject)

        elif etype == EventType.CHARACTER_EXITS:
            self._upsert_character(event.subject, {}, status=CharacterStatus.ABSENT.value)

        elif etype == EventType.CHARACTER_CHANGES:
            self._upsert_character(event.subject, event.attributes)

        elif etype == EventType.DEATH:
            # subject dies
            char_id = self._upsert_character(event.subject, {}, status=CharacterStatus.DEAD.value)
            self._record_character_upsert(result, char_id, event.subject)
            tl_id = self._create_timeline_event(event)
            result.timeline_events_created.append(tl_id)
            return  # already added timeline

        elif etype == EventType.MURDER:
            # subject kills target -> target dies
            char_id = self._upsert_character(event.subject, {})  # killer unaffected
            self._record_character_upsert(result, char_id, event.subject)
            if event.target:
                victim_id = self._upsert_character(event.target, {}, status=CharacterStatus.DEAD.value)
                self._record_character_upsert(result, victim_id, event.target)
                char_names_in_scene.extend([event.subject, event.target])

        elif etype == EventType.INJURY:
            if event.target:
                victim_id = self._upsert_character(event.target, {}, status=CharacterStatus.INJURED.value)
                self._record_character_upsert(result, victim_id, event.target)
            char_id = self._upsert_character(event.subject, {})
            self._record_character_upsert(result, char_id, event.subject)

        elif etype == EventType.TRAVEL:
            # Update last known location
            location_attrs = {"last_location": event.location} if event.location else {}
            char_id = self._upsert_character(event.subject, location_attrs,
                                             location=event.location)
            self._record_character_upsert(result, char_id, event.subject)

        elif etype in _RELATIONSHIP_EVENTS:
            if event.target:
                self._upsert_relationship(event.subject, event.target,
                                          rel_type=etype.value,
                                          attributes=event.attributes)

        # --- Timeline events ---
        if etype in _TIMELINE_EVENTS:
            tl_id = self._create_timeline_event(event)
            result.timeline_events_created.append(tl_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _record_character_upsert(self, result: MutationResult, character_id: str, name: str) -> None:
        result.character_upsert_attempts += 1
        if character_id not in result.characters_upserted:
            result.characters_upserted.append(character_id)

        normalized_name = name.strip()
        if normalized_name and all(item.get("id") != character_id for item in result.upserted_entities):
            result.upserted_entities.append({"id": character_id, "name": normalized_name})

    def _upsert_character(
        self,
        name: str,
        attributes: dict[str, Any],
        status: str | None = None,
        location: str | None = None,
    ) -> str:
        existing_list = [c for c in self._characters.list() if c.name.lower() == name.lower()]
        if existing_list:
            char = existing_list[0]
            fields: dict[str, Any] = {}
            if status:
                fields["status"] = status
            if location:
                meta = dict(char.metadata_json or {})
                meta["last_location"] = location
                fields["metadata"] = meta
            if attributes:
                meta = dict(char.metadata_json or {})
                meta.update(attributes)
                fields["metadata"] = meta
            if fields:
                self._characters.upsert(char.id, fields)
            return char.id
        else:
            if not _is_valid_character_name(name):
                logger.debug("Skipping upsert for non-name token: %r", name)
                return ""
            char_id = uuid4().hex
            meta: dict[str, Any] = dict(attributes)
            if location:
                meta["last_location"] = location
            self._characters.upsert(char_id, {
                "name": name,
                "status": status or CharacterStatus.ALIVE.value,
                "role": "supporting",
                "traits": [],
                "goals": [],
                "background": None,
                "metadata": meta,
            })
            return char_id

    def _upsert_relationship(
        self,
        source: str,
        target: str,
        rel_type: str = "related",
        attributes: dict[str, Any] | None = None,
    ) -> None:
        try:
            source_chars = [c for c in self._characters.list() if c.name.lower() == source.lower()]
            target_chars = [c for c in self._characters.list() if c.name.lower() == target.lower()]
            if not source_chars or not target_chars:
                return
            src_id = source_chars[0].id
            tgt_id = target_chars[0].id
            existing = [r for r in self._relationships.list()
                        if r.source == src_id and r.target == tgt_id]
            if existing:
                self._relationships.upsert(existing[0].id,
                                           {"relationship_type": rel_type,
                                            **(attributes or {})})
            else:
                self._relationships.create(
                    relationship_id=uuid4().hex,
                    source_id=src_id,
                    target_id=tgt_id,
                    relationship_type=rel_type,
                    strength=0.5,
                    note=None,
                    metadata={},
                )
        except Exception as exc:
            logger.warning("Relationship upsert failed (%s -> %s): %s", source, target, exc)

    def _create_timeline_event(self, event: NarrativeEvent) -> str:
        tl_id = uuid4().hex
        try:
            self._timeline.create(
                event_id=tl_id,
                title=event.predicate[:200],
                description=event.predicate,
                event_type=event.event_type.value,
                characters=[event.subject] + ([event.target] if event.target else []),
                timestamp=event.timestamp,
                metadata={
                    "source_scene": event.source_scene,
                    "location": event.location,
                    "action": event.action,
                    "is_flashback": event.is_flashback,
                    **event.attributes,
                },
            )
        except Exception as exc:
            logger.warning("Timeline event creation failed: %s", exc)
        return tl_id
