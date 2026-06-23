from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path

from backend.narrative.character.drift_detector import SemanticCharacterDriftDetector
from backend.narrative.character.memory_system import CharacterMemoryState, CharacterMemorySystem
from backend.narrative.mutation.event_generator import EventGenerator
from backend.narrative.mutation.models import ExtractedEntities
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
    happened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata_json: dict[str, object] = field(default_factory=dict)


class FakeListRepo:
    def __init__(self, items):
        self._items = list(items)

    def list(self):
        return list(self._items)


class FakeCharacterRepoMutable:
    def __init__(self, items: list[FakeCharacter]) -> None:
        self._items = items

    def list(self):
        return list(self._items)

    def upsert(self, character_id: str, fields: dict[str, object]):
        for item in self._items:
            if item.id == character_id:
                if "metadata" in fields and isinstance(fields["metadata"], dict):
                    item.metadata_json = dict(fields["metadata"])
                return item
        raise ValueError("character not found")


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


def test_event_generator_extracts_korean_colloquial_trait_relations() -> None:
    generator = EventGenerator()
    entities = ExtractedEntities()

    events = generator.generate("가원 예쁜 사람. 민수 착한 애. 철수는 귀엽고 활발하다.", entities)
    semantic_events = [event for event in events if event.event_type == EventType.CHARACTER_CHANGES]

    assert any(event.subject == "가원" and event.attributes.get("trait") == "pretty" for event in semantic_events)
    assert any(event.subject == "민수" and event.attributes.get("trait") == "kind" for event in semantic_events)
    assert any(event.subject == "철수" and event.attributes.get("trait") == "cute" for event in semantic_events)
    assert any(event.subject == "철수" and event.attributes.get("trait") == "lively" for event in semantic_events)


def test_event_generator_extracts_korean_emotion_relation() -> None:
    generator = EventGenerator()

    events = generator.generate("유리는 지금 화나 있다.", ExtractedEntities())
    semantic_events = [event for event in events if event.event_type == EventType.CHARACTER_CHANGES]

    assert any(
        event.subject == "유리"
        and event.attributes.get("relation_type") == "has_emotion"
        and event.attributes.get("emotion") == "angry"
        for event in semantic_events
    )


def test_event_generator_maps_additional_korean_synonyms() -> None:
    generator = EventGenerator()
    events = generator.generate(
        "가원 오늘 좀 이상하다. 민수 분위기가 싸하다. 철수 눈빛이 무섭다. 유리는 평소랑 달랐다.",
        ExtractedEntities(),
    )
    semantic_events = [event for event in events if event.event_type == EventType.CHARACTER_CHANGES]

    assert any(event.subject == "가원" and event.attributes.get("trait") == "eccentric" for event in semantic_events)
    assert any(event.subject == "민수" and event.attributes.get("emotion") == "uneasy" for event in semantic_events)
    assert any(event.subject == "철수" and event.attributes.get("trait") == "scary" for event in semantic_events)
    assert any(event.subject == "유리" and event.attributes.get("trait") == "different" for event in semantic_events)


def test_event_generator_maps_funny_handsome_and_proactive_descriptors() -> None:
    generator = EventGenerator()
    events = generator.generate("현수, 재밌는 사람이다, 잘 생겼다, 적극적으로 사람이다", ExtractedEntities())
    semantic_events = [event for event in events if event.event_type == EventType.CHARACTER_CHANGES]

    assert any(event.subject == "현수" and event.attributes.get("trait") == "funny" for event in semantic_events)
    assert any(event.subject == "현수" and event.attributes.get("trait") == "handsome" for event in semantic_events)
    assert any(event.subject == "현수" and event.attributes.get("trait") == "proactive" for event in semantic_events)


def test_event_generator_maps_bad_descriptor() -> None:
    generator = EventGenerator()
    events = generator.generate("황링은 나쁜 사람이다", ExtractedEntities())
    semantic_events = [event for event in events if event.event_type == EventType.CHARACTER_CHANGES]

    assert any(event.subject == "황링" and event.attributes.get("trait") == "bad" for event in semantic_events)


def test_character_memory_confidence_gate_splits_permanent_and_pending() -> None:
    repo = FakeCharacterRepoMutable([FakeCharacter(id="char-1", name="가원")])
    memory_system = CharacterMemorySystem(repo, confidence_threshold=0.72, pending_threshold=0.35)

    high_conf_event = NarrativeEvent(
        event_type=EventType.CHARACTER_CHANGES,
        subject="가원",
        predicate="가원 has trait pretty",
        attributes={
            "relation_type": "has_trait",
            "trait": "pretty",
            "surface_descriptor": "예쁜",
            "semantic_confidence": 0.9,
        },
    )
    low_conf_event = NarrativeEvent(
        event_type=EventType.CHARACTER_CHANGES,
        subject="가원",
        predicate="가원 has trait provisional",
        attributes={
            "relation_type": "has_trait",
            "trait": "provisional:싸하다",
            "surface_descriptor": "싸하다",
            "semantic_confidence": 0.46,
            "provisional": True,
        },
    )

    memory_system.update_from_events([high_conf_event, low_conf_event])
    memory = memory_system.get_memory("가원")

    assert any(item.get("trait") == "pretty" for item in memory.trait_events)
    assert any(item.get("trait") == "provisional:싸하다" for item in memory.pending_trait_events)
    assert not any(item.get("trait") == "provisional:싸하다" for item in memory.trait_events)


def test_event_generator_keeps_unknown_descriptor_as_provisional_trait() -> None:
    generator = EventGenerator()
    events = generator.generate("준호 분위기가 묘하다.", ExtractedEntities())
    semantic_events = [event for event in events if event.event_type == EventType.CHARACTER_CHANGES]

    assert any(
        event.subject == "준호"
        and str(event.attributes.get("trait", "")).startswith("provisional:")
        and event.attributes.get("provisional") is True
        for event in semantic_events
    )


def test_character_memory_promotion_job_promotes_repeated_pending_traits() -> None:
    repo = FakeCharacterRepoMutable([
        FakeCharacter(
            id="char-1",
            name="민수",
            metadata_json={
                "memory": {
                    "pending_trait_events": [
                        {
                            "trait": "provisional:싸하다",
                            "relation": "has_emotion",
                            "confidence": 0.5,
                            "source_scene": "s1",
                            "timestamp": "2025-01-01T00:00:00+00:00",
                        },
                        {
                            "trait": "provisional:싸하다",
                            "relation": "has_emotion",
                            "confidence": 0.55,
                            "source_scene": "s2",
                            "timestamp": "2025-01-02T00:00:00+00:00",
                        },
                    ]
                }
            },
        )
    ])
    memory_system = CharacterMemorySystem(
        repo,
        confidence_threshold=0.72,
        pending_threshold=0.35,
        promotion_min_occurrences=2,
        promotion_min_distinct_scenes=2,
        promotion_min_average_confidence=0.45,
    )

    summary = memory_system.promote_pending_traits()
    memory = memory_system.get_memory("민수")

    assert summary["promoted_entries"] == 2
    assert summary["promoted_characters"] == 1
    assert len(memory.pending_trait_events) == 0
    assert any(item.get("trait") == "provisional:싸하다" for item in memory.trait_events)


def test_character_memory_confidence_histogram_reports_pending_and_permanent() -> None:
    repo = FakeCharacterRepoMutable([
        FakeCharacter(
            id="char-1",
            name="가원",
            metadata_json={
                "memory": {
                    "trait_events": [
                        {"trait": "pretty", "confidence": 0.9, "source_scene": "s1", "timestamp": "2025-01-01T00:00:00+00:00"},
                        {"trait": "cute", "confidence": 0.8, "source_scene": "s1", "timestamp": "2025-01-01T00:00:01+00:00"},
                    ],
                    "pending_trait_events": [
                        {"trait": "provisional:묘하다", "confidence": 0.46, "source_scene": "s2", "timestamp": "2025-01-02T00:00:00+00:00"},
                    ],
                }
            },
        )
    ])
    memory_system = CharacterMemorySystem(repo)

    histogram = memory_system.confidence_histogram(character_name="가원", bucket_size=0.1)

    assert histogram["character_count"] == 1
    character_block = histogram["characters"]["가원"]
    assert character_block["counts"]["permanent"] == 2
    assert character_block["counts"]["pending"] == 1
    assert any(bucket["bucket"].startswith("0.40") for bucket in character_block["pending"])
