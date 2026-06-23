from __future__ import annotations

from dataclasses import dataclass, field

from backend.narrative.mutation.models import EventType, NarrativeEvent
from backend.narrative.world.canon_registry import CanonRegistry
from backend.narrative.world.lore_manager import LoreManager


@dataclass(slots=True)
class CanonConflict:
    rule_id: str
    message: str
    severity: str = "error"
    entities: list[str] = field(default_factory=list)


class CanonProtectionLayer:
    """Protects immutable canon and flags lore conflicts before/after mutation."""

    def __init__(
        self,
        canon_registry: CanonRegistry | None = None,
        lore_manager: LoreManager | None = None,
    ) -> None:
        self._canon = canon_registry
        self._lore = lore_manager

    def check_events(
        self,
        events: list[NarrativeEvent],
        allow_override: bool = False,
    ) -> list[CanonConflict]:
        conflicts: list[CanonConflict] = []
        for event in events:
            conflicts.extend(self._check_immutable_canon(event, allow_override))
            conflicts.extend(self._check_lore_conflict(event))
        return conflicts

    def _check_immutable_canon(self, event: NarrativeEvent, allow_override: bool) -> list[CanonConflict]:
        if self._canon is None or allow_override:
            return []
        conflicts: list[CanonConflict] = []
        keys = [event.subject, event.target, event.location]
        for key in [item for item in keys if item]:
            entry = self._canon.get(str(key))
            if entry is None:
                continue
            if not entry.immutable:
                continue
            if event.event_type == EventType.DEATH and entry.value.lower() in {"immortal", "cannot die"}:
                conflicts.append(CanonConflict(
                    rule_id="canon_immutable_override",
                    message=f"Immutable canon says {event.subject} is '{entry.value}', but event implies death.",
                    entities=[event.subject],
                ))
            if event.event_type == EventType.RESURRECTION and entry.value.lower() in {"resurrection forbidden", "cannot return"}:
                conflicts.append(CanonConflict(
                    rule_id="canon_immutable_override",
                    message=f"Immutable canon forbids resurrection for {event.subject}.",
                    entities=[event.subject],
                ))
        return conflicts

    def _check_lore_conflict(self, event: NarrativeEvent) -> list[CanonConflict]:
        if self._lore is None:
            return []
        query_terms = " ".join(item for item in [event.subject, event.target, event.location, event.action] if item)
        if not query_terms.strip():
            return []
        related = self._lore.search(query_terms)
        conflicts: list[CanonConflict] = []
        predicate_lower = event.predicate.lower()
        for fact in related:
            value = fact.value.lower()
            if "forbidden" in value and any(word in predicate_lower for word in ["resurrect", "murder", "betray"]):
                conflicts.append(CanonConflict(
                    rule_id="lore_conflict_detected",
                    message=f"Event '{event.predicate}' conflicts with lore fact '{fact.key}: {fact.value}'.",
                    entities=[event.subject] + ([event.target] if event.target else []),
                    severity="warning",
                ))
        return conflicts
