from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from backend.consistency import MultiAgentNarrativeAnalyzer, SemanticValidator
from backend.narrative.mutation.models import EventType, NarrativeEvent
from backend.narrative.state_engine import NarrativeStateMutationEngine


@dataclass
class FakeCharacter:
    id: str
    name: str
    role: str = "supporting"
    background: str | None = None
    traits: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    status: str = "alive"
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass
class FakeScene:
    id: str
    title: str
    summary: str | None = None
    beats: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)


@dataclass
class FakeTimelineEvent:
    id: str
    title: str
    description: str | None = None
    happened_at: datetime = field(
    default_factory=lambda: datetime.now(UTC))
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass
class FakeRelationship:
    id: str
    source: str
    target: str
    relationship_type: str
    strength: float = 0.5
    notes: list[str] = field(default_factory=list)


class FakeCharacterRepo:
    def __init__(self, items: list[FakeCharacter] | None = None) -> None:
        self._items: dict[str, FakeCharacter] = {item.id: item for item in (items or [])}

    def list(self):
        return list(self._items.values())

    def upsert(self, character_id: str, patch: dict[str, Any]):
        character = self._items.get(character_id)
        if character is None:
            character = FakeCharacter(
                id=character_id,
                name=str(patch.get("name") or character_id),
                role=str(patch.get("role") or "supporting"),
                traits=list(patch.get("traits") or []),
                goals=list(patch.get("goals") or []),
                background=patch.get("background"),
                status=str(patch.get("status") or "alive"),
                metadata_json=dict(patch.get("metadata") or {}),
            )
            self._items[character_id] = character
            return character

        if "name" in patch and patch["name"] is not None:
            character.name = str(patch["name"])
        if "role" in patch and patch["role"] is not None:
            character.role = str(patch["role"])
        if "status" in patch and patch["status"] is not None:
            character.status = str(patch["status"])
        if "traits" in patch and patch["traits"] is not None:
            character.traits = list(patch["traits"])
        if "goals" in patch and patch["goals"] is not None:
            character.goals = list(patch["goals"])
        if "background" in patch:
            character.background = patch["background"]
        if "metadata" in patch and patch["metadata"] is not None:
            character.metadata_json = dict(patch["metadata"])
        return character


class FakeSceneRepo:
    def __init__(self) -> None:
        self._items: list[FakeScene] = []

    def create(self, title: str, summary: str | None, beats: list[str], characters: list[str]):
        scene = FakeScene(
            id=f"scene-{len(self._items) + 1}",
            title=title,
            summary=summary,
            beats=list(beats),
            characters=list(characters),
        )
        self._items.append(scene)
        return scene

    def list(self):
        return list(self._items)


class FakeTimelineRepo:
    def __init__(self) -> None:
        self._items: list[FakeTimelineEvent] = []

    def create(
        self,
        event_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        event_type: str | None = None,
        characters: list[str] | None = None,
        timestamp: datetime | None = None,
        metadata: dict[str, object] | None = None,
        happened_at: datetime | None = None,
    ):
        event = FakeTimelineEvent(
            id=event_id or f"timeline-{len(self._items) + 1}",
            title=title or event_type or "timeline",
            description=description,
            happened_at=timestamp or happened_at or datetime.now(UTC),
            metadata_json=dict(metadata or {}),
        )
        self._items.append(event)
        return event

    def list(self):
        return list(self._items)


class FakeRelationshipRepo:
    def __init__(self) -> None:
        self._items: list[FakeRelationship] = []

    def list(self, character_id: str | None = None):
        if character_id is None:
            return list(self._items)
        return [item for item in self._items if item.source == character_id or item.target == character_id]

    def create(self, **kwargs):
        relationship = FakeRelationship(
            id=kwargs.get("relationship_id") or f"rel-{len(self._items) + 1}",
            source=str(kwargs.get("source") or kwargs.get("source_id") or ""),
            target=str(kwargs.get("target") or kwargs.get("target_id") or ""),
            relationship_type=str(kwargs.get("relationship_type") or "ally"),
            strength=float(kwargs.get("strength") or 0.5),
            notes=list(kwargs.get("notes") or []),
        )
        self._items.append(relationship)
        return relationship

    def upsert(self, relationship_id: str, patch: dict[str, object]):
        for item in self._items:
            if item.id == relationship_id:
                if "relationship_type" in patch:
                    item.relationship_type = str(patch["relationship_type"])
                if "strength" in patch and patch["strength"] is not None:
                    item.strength = float(patch["strength"])
                if "notes" in patch and patch["notes"] is not None:
                    item.notes = list(patch["notes"])
                return item
        return self.create(relationship_id=relationship_id, **patch)


class FakeLoreFact:
    def __init__(self, key: str, value: str, source: str | None = None, tags: list[str] | None = None) -> None:
        self.key = key
        self.value = value
        self.source = source
        self.tags = tags or []


class FakeLoreRepo:
    def __init__(self, facts: list[FakeLoreFact] | None = None) -> None:
        self._facts = list(facts or [])

    def list(self):
        return list(self._facts)

    def search(self, query: str):
        lowered = query.lower()
        return [
            fact
            for fact in self._facts
            if fact.key.lower() in lowered or any(token in fact.value.lower() for token in lowered.split())
        ]


class FakeCanonRepo:
    def list(self):
        return []

    def get(self, key: str):
        return None


def _event(event_type: EventType, subject: str, predicate: str, **kwargs) -> NarrativeEvent:
    return NarrativeEvent(event_type=event_type, subject=subject, predicate=predicate, **kwargs)


def test_semantic_validator_detects_phase4_issue_categories() -> None:
    validator = SemanticValidator()
    events = [
        _event(EventType.MURDER, "John", "John kills Mira", target="Mira"),
        _event(EventType.MARRIAGE, "John", "John marries Mira", target="Mira"),
    ]
    text = 'John laughed as Mira collapsed. "I never trust Mira," he said. He smiled: "I trust Mira with my life."'

    result = validator.validate(text, references=["Mira is John's trusted ally"], events=events)

    categories = {issue.category for issue in result.issues}
    assert "emotional_mismatch" in categories
    assert "dialogue_inconsistency" in categories
    assert "unnatural_progression" in categories
    assert result.score < 1.0


def test_multi_agent_narrative_analysis_maps_required_roles() -> None:
    analyzer = MultiAgentNarrativeAnalyzer()
    events = [
        _event(EventType.MURDER, "John", "John kills Mira", target="Mira"),
        _event(EventType.ALLIANCE, "John", "John forms alliance with Aria", target="Aria"),
    ]

    report = analyzer.analyze(
        text="John kills Mira then suddenly forms an alliance with Aria.",
        events=events,
        references=["Mira is protected by sacred law"],
        character_names=["John", "Mira", "Aria"],
        character_memories={},
        canon_conflicts=[],
        drift_issues=[],
        chronology_conflicts=[],
        flashback_count=0,
        flash_forward_count=0,
        semantic_issues=[],
    )

    payload = report.as_dict()
    assert set(payload["agents"].keys()) == {"lore", "character", "timeline", "critic"}
    assert payload["agents"]["lore"]["role"] == "canon"
    assert payload["agents"]["character"]["role"] == "personality"
    assert payload["agents"]["timeline"]["role"] == "chronology"
    assert payload["agents"]["critic"]["role"] == "pacing"


def test_state_engine_process_scene_returns_phase4_outputs(tmp_path: Path) -> None:
    cache_path = tmp_path / "memory-index.json"
    event_path = tmp_path / "events.jsonl"
    snapshot_path = tmp_path / "snapshots.json"
    branch_path = tmp_path / "branches.json"

    repositories: dict[str, Any] = {
    "canon": FakeCanonRepo(),
    "character": FakeCharacterRepo([
        FakeCharacter(
            id="char-john",
            name="John",
            metadata_json={
                "memory": {
                    "personality": ["emotion:joyful"],
                    "beliefs": []
                }
            },
        ),
        FakeCharacter(id="char-mira", name="Mira"),
    ]),
    "lore": FakeLoreRepo([
        FakeLoreFact(key="oath", value="Betrayal is forbidden")
    ]),
    "relationship": FakeRelationshipRepo(),
    "scene": FakeSceneRepo(),
    "timeline": FakeTimelineRepo(),
}

    engine = NarrativeStateMutationEngine(repositories, llm_provider=None)
    engine._memory._cache_path = cache_path
    engine._event_store._file_path = event_path
    engine._vcs.snapshots._file_path = snapshot_path
    engine._vcs.branches._file_path = branch_path

    result = engine.process_scene(
        "John killed Mira. He laughed and suddenly celebrated. \"I never trust Mira,\" John said. Moments later he added, \"I trust Mira.\"",
        {"scene_title": "Phase4 Demo", "branch": "main"},
    )

    assert result["success"] is True
    assert "semantic_validation" in result
    assert "multi_agent_analysis" in result
    assert isinstance(result["semantic_validation"]["issues"], list)
    assert set(result["multi_agent_analysis"]["agents"].keys()) == {"lore", "character", "timeline", "critic"}
    assert any(item["rule_id"] in {"semantic_emotional_mismatch", "dialogue_inconsistency", "unnatural_progression"} for item in result["writer_warnings"])
