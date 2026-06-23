from __future__ import annotations

from dataclasses import dataclass, field

from backend.narrative.character.memory_system import CharacterMemoryState
from backend.narrative.mutation.models import EventType, NarrativeEvent


@dataclass(slots=True)
class DriftIssue:
    rule_id: str
    severity: str
    character: str
    message: str
    evidence: list[str] = field(default_factory=list)


class SemanticCharacterDriftDetector:
    """Detects personality collapse, emotional inconsistency, and irrational actions."""

    def detect(
        self,
        events: list[NarrativeEvent],
        character_memories: dict[str, CharacterMemoryState],
    ) -> list[DriftIssue]:
        issues: list[DriftIssue] = []
        for event in events:
            memory = character_memories.get(event.subject)
            if memory is None:
                continue
            issues.extend(self._check_pacifist_collapse(event, memory))
            issues.extend(self._check_emotional_inconsistency(event, memory))
            issues.extend(self._check_irrational_action(event, memory))
        return issues

    def _check_pacifist_collapse(self, event: NarrativeEvent, memory: CharacterMemoryState) -> list[DriftIssue]:
        pacifist_markers = {item.lower() for item in (memory.personality + memory.beliefs)}
        if not any("pacifist" in item or "never kill" in item or "abhors violence" in item for item in pacifist_markers):
            return []
        if event.event_type not in {EventType.MURDER, EventType.CONFLICT, EventType.INJURY}:
            return []
        return [DriftIssue(
            rule_id="personality_collapse",
            severity="error",
            character=event.subject,
            message=f"{event.subject} is established as pacifist but performs violent action '{event.predicate}'.",
            evidence=sorted(pacifist_markers),
        )]

    def _check_emotional_inconsistency(self, event: NarrativeEvent, memory: CharacterMemoryState) -> list[DriftIssue]:
        emotions = [item for item in memory.personality if item.startswith("emotion:")]
        current_emotion = str(event.attributes.get("emotion") or "").lower()
        if not emotions or not current_emotion:
            return []
        if any(emotion.endswith(current_emotion) for emotion in emotions):
            return []
        if current_emotion in {"joyful", "happy", "delighted"} and event.event_type in {EventType.MURDER, EventType.DEATH}:
            return [DriftIssue(
                rule_id="emotional_inconsistency",
                severity="warning",
                character=event.subject,
                message=f"{event.subject} displays '{current_emotion}' during lethal event '{event.predicate}'.",
                evidence=emotions,
            )]
        return []

    def _check_irrational_action(self, event: NarrativeEvent, memory: CharacterMemoryState) -> list[DriftIssue]:
        desires = {item.lower() for item in memory.desires}
        beliefs = {item.lower() for item in memory.beliefs}
        if event.event_type == EventType.BETRAYAL and any("loyal" in item or "protect" in item for item in beliefs | desires):
            return [DriftIssue(
                rule_id="irrational_action",
                severity="warning",
                character=event.subject,
                message=f"{event.subject} performs betrayal despite established loyalty-oriented memory.",
                evidence=sorted(beliefs | desires),
            )]
        if event.event_type == EventType.TRAVEL and event.location and any(event.location.lower() in item and "avoid" in item for item in beliefs):
            return [DriftIssue(
                rule_id="irrational_action",
                severity="warning",
                character=event.subject,
                message=f"{event.subject} travels to {event.location} despite beliefs indicating avoidance.",
                evidence=sorted(beliefs),
            )]
        return []
