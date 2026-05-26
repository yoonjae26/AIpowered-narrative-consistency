from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from backend.narrative.character.drift_detector import SemanticCharacterDriftDetector
from backend.narrative.character.memory_system import CharacterMemoryState
from backend.narrative.mutation.models import EventType, NarrativeEvent
from backend.narrative.world.canon_protection import CanonProtectionLayer
from backend.rag.context_builder.narrative_memory import NarrativeMemoryService


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
class FakeLoreFact:
    key: str
    value: str
    source: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class FakeTimelineEvent:
    id: str
    title: str
    description: str | None = None
    happened_at: datetime = field(default_factory=datetime.utcnow)
    metadata_json: dict[str, object] = field(default_factory=dict)


class FakeListRepo:
    def __init__(self, items):
        self._items = list(items)

    def list(self):
        return list(self._items)


class FakeCanonEntry:
    def __init__(self, key: str, value: str, immutable: bool = True):
        self.key = key
        self.value = value
        self.immutable = immutable
        self.aliases = []


class FakeCanonRegistry:
    def __init__(self, entries: dict[str, FakeCanonEntry]):
        self._entries = entries

    def get(self, key: str):
        return self._entries.get(key)


class FakeLoreManager:
    def __init__(self, facts: list[FakeLoreFact]):
        self._facts = facts

    def search(self, query: str):
        query_lower = query.lower()
        return [fact for fact in self._facts if fact.key.lower() in query_lower or any(token in fact.value.lower() for token in query_lower.split())]


def test_narrative_memory_persists_index_to_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "narrative_memory_index.json"
    service = NarrativeMemoryService(
        scene_repo=FakeListRepo([
            FakeScene(id="scene-1", title="Castle Betrayal", summary="John kills Anna", beats=["John killed Anna in the castle"], characters=["John", "Anna"]),
        ]),
        lore_repo=FakeListRepo([
            FakeLoreFact(key="castle", value="The castle is ancient and cursed", source="canon", tags=["location"]),
        ]),
        character_repo=FakeListRepo([
            FakeCharacter(id="char-1", name="John", traits=["grim"], metadata_json={"memory": {"beliefs": ["protect Anna"]}}),
        ]),
        timeline_repo=FakeListRepo([
            FakeTimelineEvent(id="event-1", title="Murder", description="John kills Anna", metadata_json={"location": "castle"}),
        ]),
        cache_path=cache_path,
    )

    service.rebuild_index()
    assert cache_path.exists()

    reloaded = NarrativeMemoryService(cache_path=cache_path)
    hits = reloaded.search("Castle Betrayal Anna castle", limit=10)

    assert hits
    assert any(hit.source_type == "scene" for hit in hits)
    assert any(hit.source_type == "event" for hit in hits)


def test_drift_detector_flags_pacifist_murder() -> None:
    detector = SemanticCharacterDriftDetector()
    memories = {
        "John": CharacterMemoryState(
            personality=["pacifist"],
            beliefs=["never kill"],
            knowledge=[],
            desires=[],
        )
    }
    events = [
        NarrativeEvent(
            event_type=EventType.MURDER,
            subject="John",
            target="Anna",
            predicate="John kills Anna",
            action="killed",
        )
    ]

    issues = detector.detect(events, memories)

    assert len(issues) == 1
    assert issues[0].rule_id == "personality_collapse"
    assert issues[0].severity == "error"
    assert "pacifist" in issues[0].message


def test_canon_protection_blocks_immutable_canon_and_flags_lore_conflict() -> None:
    layer = CanonProtectionLayer(
        canon_registry=FakeCanonRegistry({
            "John": FakeCanonEntry(key="John", value="immortal", immutable=True),
        }),
        lore_manager=FakeLoreManager([
            FakeLoreFact(key="betray", value="Betrayal is forbidden by royal law"),
        ]),
    )
    events = [
        NarrativeEvent(
            event_type=EventType.DEATH,
            subject="John",
            predicate="John dies in battle",
        ),
        NarrativeEvent(
            event_type=EventType.BETRAYAL,
            subject="Mira",
            target="Crown",
            predicate="Mira betrays the Crown",
            action="betrayed",
        ),
    ]

    conflicts = layer.check_events(events)

    assert len(conflicts) == 2
    assert any(conflict.rule_id == "canon_immutable_override" for conflict in conflicts)
    assert any(conflict.rule_id == "lore_conflict_detected" for conflict in conflicts)
