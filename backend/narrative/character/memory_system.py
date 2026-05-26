from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.database.repositories.character_repository import CharacterRepository
from backend.narrative.mutation.models import EventType, NarrativeEvent


@dataclass(slots=True)
class CharacterMemoryState:
    personality: list[str] = field(default_factory=list)
    beliefs: list[str] = field(default_factory=list)
    knowledge: list[str] = field(default_factory=list)
    desires: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "personality": list(dict.fromkeys(self.personality)),
            "beliefs": list(dict.fromkeys(self.beliefs)),
            "knowledge": list(dict.fromkeys(self.knowledge)),
            "desires": list(dict.fromkeys(self.desires)),
        }


class CharacterMemorySystem:
    """Persistent PKBD memory stored in Character.metadata_json['memory']."""

    def __init__(self, character_repo: CharacterRepository) -> None:
        self._characters = character_repo

    def get_memory(self, character_name: str) -> CharacterMemoryState:
        character = self._find_character(character_name)
        if character is None:
            return CharacterMemoryState()
        metadata = character.metadata_json or {}
        memory = metadata.get("memory", {}) if isinstance(metadata, dict) else {}
        return CharacterMemoryState(
            personality=list(memory.get("personality", [])),
            beliefs=list(memory.get("beliefs", [])),
            knowledge=list(memory.get("knowledge", [])),
            desires=list(memory.get("desires", [])),
        )

    def update_from_events(self, events: list[NarrativeEvent]) -> dict[str, CharacterMemoryState]:
        updated: dict[str, CharacterMemoryState] = {}
        for event in events:
            if self._find_character(event.subject) is None:
                continue
            memory = self.get_memory(event.subject)
            self._apply_subject_event(memory, event)
            self._persist(event.subject, memory)
            updated[event.subject] = memory
            if event.target and self._find_character(event.target) is not None:
                target_memory = self.get_memory(event.target)
                self._apply_target_event(target_memory, event)
                self._persist(event.target, target_memory)
                updated[event.target] = target_memory
        return updated

    def _apply_subject_event(self, memory: CharacterMemoryState, event: NarrativeEvent) -> None:
        if event.event_type == EventType.MURDER:
            memory.knowledge.append(f"committed murder of {event.target}")
        elif event.event_type == EventType.DISCOVERY:
            memory.knowledge.append(event.predicate)
        elif event.event_type == EventType.TRAVEL and event.location:
            memory.knowledge.append(f"visited {event.location}")
        elif event.event_type == EventType.ALLIANCE and event.target:
            memory.beliefs.append(f"trusts {event.target}")
        elif event.event_type == EventType.BETRAYAL and event.target:
            memory.beliefs.append(f"betrayed {event.target}")
        elif event.event_type == EventType.CONFLICT and event.target:
            memory.beliefs.append(f"in conflict with {event.target}")
        self._append_from_attributes(memory, event.attributes)

    def _apply_target_event(self, memory: CharacterMemoryState, event: NarrativeEvent) -> None:
        if event.event_type == EventType.MURDER and event.subject:
            memory.knowledge.append(f"was murdered by {event.subject}")
        elif event.event_type == EventType.INJURY and event.subject:
            memory.knowledge.append(f"was injured by {event.subject}")
        elif event.event_type == EventType.MARRIAGE and event.subject:
            memory.beliefs.append(f"married to {event.subject}")
        elif event.event_type == EventType.ALLIANCE and event.subject:
            memory.beliefs.append(f"allied with {event.subject}")

    def _append_from_attributes(self, memory: CharacterMemoryState, attributes: dict[str, Any]) -> None:
        if not isinstance(attributes, dict):
            return
        role = attributes.get("role")
        emotion = attributes.get("emotion")
        action = attributes.get("action")
        desire = attributes.get("desire")
        belief = attributes.get("belief")
        if isinstance(role, str) and role:
            memory.personality.append(role)
        if isinstance(emotion, str) and emotion:
            memory.personality.append(f"emotion:{emotion}")
        if isinstance(action, str) and action:
            memory.knowledge.append(action)
        if isinstance(desire, str) and desire:
            memory.desires.append(desire)
        if isinstance(belief, str) and belief:
            memory.beliefs.append(belief)

    def _persist(self, character_name: str, memory: CharacterMemoryState) -> None:
        character = self._find_character(character_name)
        if character is None:
            return
        metadata = dict(character.metadata_json or {})
        metadata["memory"] = memory.as_dict()
        self._characters.upsert(character.id, {"metadata": metadata})

    def _find_character(self, character_name: str):
        for character in self._characters.list():
            if character.name.lower() == character_name.lower():
                return character
        return None
