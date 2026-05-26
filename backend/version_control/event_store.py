from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.narrative.reality import (
    CHARACTER_SUBJECT_EVENT_TYPES,
    CHARACTER_TARGET_EVENT_TYPES,
    RELATIONSHIP_EVENT_TYPES,
    event_order_key,
)


@dataclass(slots=True)
class StoredNarrativeEvent:
    id: str
    branch: str
    event_type: str
    subject: str
    predicate: str
    target: str | None = None
    action: str | None = None
    location: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    source_scene: str | None = None
    origin_event_id: str | None = None
    operation: str = "append"
    happened_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventStore:
    """Append-only event log persisted as JSONL for replay, rollback, and branching."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file_path = Path(file_path or ".cache/narrative_event_store.jsonl")
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def append_events(self, events: list[Any], branch: str = "main") -> list[StoredNarrativeEvent]:
        stored: list[StoredNarrativeEvent] = []
        if not events:
            return stored
        with self._file_path.open("a", encoding="utf-8") as handle:
            for event in events:
                item = self._to_stored_event(event, branch)
                handle.write(json.dumps(asdict(item), ensure_ascii=True) + "\n")
                stored.append(item)
        return stored

    def append_stored_events(
        self,
        events: list[StoredNarrativeEvent],
        branch: str,
        operation: str = "cherry-pick",
    ) -> list[StoredNarrativeEvent]:
        cloned: list[StoredNarrativeEvent] = []
        if not events:
            return cloned
        with self._file_path.open("a", encoding="utf-8") as handle:
            for event in events:
                copied = StoredNarrativeEvent(
                    id=uuid4().hex,
                    branch=branch,
                    origin_event_id=event.origin_event_id or event.id,
                    operation=operation,
                    event_type=event.event_type,
                    subject=event.subject,
                    predicate=event.predicate,
                    target=event.target,
                    action=event.action,
                    location=event.location,
                    attributes=dict(event.attributes),
                    source_scene=event.source_scene,
                    happened_at=event.happened_at,
                )
                handle.write(json.dumps(asdict(copied), ensure_ascii=True) + "\n")
                cloned.append(copied)
        return cloned

    def list_events(self, branch: str | None = None) -> list[StoredNarrativeEvent]:
        if not self._file_path.exists():
            return []
        results: list[StoredNarrativeEvent] = []
        with self._file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                item = StoredNarrativeEvent(**raw)
                if branch is None or item.branch == branch:
                    results.append(item)
        return results

    def head_event_id(self, branch: str = "main") -> str | None:
        events = self.list_events(branch=branch)
        return events[-1].id if events else None

    def rollback_view(self, branch: str, to_event_id: str | None) -> list[StoredNarrativeEvent]:
        events = self.list_events(branch=branch)
        if to_event_id is None:
            return []
        kept: list[StoredNarrativeEvent] = []
        for event in events:
            kept.append(event)
            if event.id == to_event_id:
                break
        return kept

    def replay_state(self, branch: str = "main", to_event_id: str | None = None) -> dict[str, Any]:
        return self.replay_events(self.list_events(branch=branch), to_event_id=to_event_id)

    def replay_events(self, events: list[StoredNarrativeEvent], to_event_id: str | None = None) -> dict[str, Any]:
        ordered_events = sorted(events, key=event_order_key)
        state = {
            "characters": {},
            "relationships": [],
            "locations": {},
            "knowledge": {},
            "scene_history": [],
            "event_count": 0,
        }
        for event in ordered_events:
            state["event_count"] += 1
            if event.source_scene and event.source_scene not in state["scene_history"]:
                state["scene_history"].append(event.source_scene)
            self._reduce(state, event)
            if to_event_id and event.id == to_event_id:
                break
        return state

    def _reduce(self, state: dict[str, Any], event: StoredNarrativeEvent) -> None:
        characters = state["characters"]
        knowledge = state["knowledge"]
        locations = state["locations"]

        if event.subject and event.event_type in CHARACTER_SUBJECT_EVENT_TYPES:
            characters.setdefault(event.subject, {"status": "alive", "last_location": None})
            knowledge.setdefault(event.subject, [])
        if event.target and event.event_type in CHARACTER_TARGET_EVENT_TYPES:
            characters.setdefault(event.target, {"status": "alive", "last_location": None})
            knowledge.setdefault(event.target, [])

        if event.event_type == "murder":
            if event.target:
                characters[event.target]["status"] = "dead"
            knowledge[event.subject].append(f"killed {event.target}")
        elif event.event_type == "death":
            characters[event.subject]["status"] = "dead"
        elif event.event_type == "resurrection":
            characters[event.subject]["status"] = "alive"
        elif event.event_type == "injury" and event.target:
            characters[event.target]["status"] = "injured"
        elif event.event_type == "travel" and event.location:
            characters[event.subject]["last_location"] = event.location
            locations[event.subject] = event.location
        elif event.event_type in RELATIONSHIP_EVENT_TYPES:
            state["relationships"].append({
                "source": event.subject,
                "target": event.target,
                "relationship_type": event.event_type,
                "strength": event.attributes.get("strength", 0.5),
            })
        elif event.event_type == "discovery":
            knowledge[event.subject].append(event.predicate)

    def _to_stored_event(self, event: Any, branch: str) -> StoredNarrativeEvent:
        happened_at = getattr(event, "timestamp", None)
        return StoredNarrativeEvent(
            id=uuid4().hex,
            branch=branch,
            origin_event_id=None,
            operation="append",
            event_type=getattr(event, "event_type").value,
            subject=getattr(event, "subject", ""),
            predicate=getattr(event, "predicate", ""),
            target=getattr(event, "target", None),
            action=getattr(event, "action", None),
            location=getattr(event, "location", None),
            attributes=dict(getattr(event, "attributes", {}) or {}),
            source_scene=getattr(event, "source_scene", None),
            happened_at=happened_at.isoformat() if happened_at else datetime.now(UTC).isoformat(),
        )
