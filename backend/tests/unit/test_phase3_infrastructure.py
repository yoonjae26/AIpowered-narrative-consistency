from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.narrative.query_system import NarrativeQuerySystem
from backend.narrative.relationships.graph import RelationshipGraph
from backend.narrative.relationships.relationship_types import RelationshipType
from backend.rag.context_builder.narrative_memory import NarrativeMemoryService
from backend.version_control import BranchManager, EventStore, SnapshotManager, StoryVersionControl
from backend.narrative.mutation.models import EventType, NarrativeEvent


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
class FakeRelationship:
    id: int
    source: str
    target: str
    relationship_type: str
    strength: float
    notes: list[str] = field(default_factory=list)


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


class FakeCharacterRepo:
    def __init__(self, items: list[FakeCharacter]) -> None:
        self._items = items

    def list(self):
        return list(self._items)


class FakeListRepo:
    def __init__(self, items):
        self._items = list(items)

    def list(self):
        return list(self._items)


class FakeRelationshipRepo:
    def __init__(self, items: list[FakeRelationship] | None = None) -> None:
        self._items = list(items or [])

    def list(self, character_id: str | None = None):
        if character_id is None:
            return list(self._items)
        return [item for item in self._items if item.source == character_id or item.target == character_id]

    def create(self, source: str, target: str, relationship_type: str, strength: float, notes: list[str]):
        created = FakeRelationship(
            id=len(self._items) + 1,
            source=source,
            target=target,
            relationship_type=relationship_type,
            strength=strength,
            notes=notes,
        )
        self._items.append(created)
        return created


def _event(event_type: EventType, subject: str, predicate: str, **kwargs) -> NarrativeEvent:
    return NarrativeEvent(event_type=event_type, subject=subject, predicate=predicate, **kwargs)


def test_event_sourcing_replay_and_branching(tmp_path: Path) -> None:
    vcs = StoryVersionControl(
        event_store=EventStore(tmp_path / "events.jsonl"),
        snapshot_manager=SnapshotManager(tmp_path / "snapshots.json"),
        branch_manager=BranchManager(tmp_path / "branches.json"),
    )

    base_commit = vcs.append_commit(
        title="Anna dies",
        events=[_event(EventType.MURDER, "John", "John kills Anna", target="Anna")],
        derived_state={},
    )

    vcs.create_branch("anna-survives")
    vcs.checkout("anna-survives")
    alt_commit = vcs.append_commit(
        title="Anna escapes",
        events=[_event(EventType.TRAVEL, "Anna", "Anna escapes to the forest", location="forest")],
        derived_state={},
    )

    main_state = vcs.replay(branch="main")
    alt_state = vcs.replay(branch="anna-survives")
    diff = vcs.diff_snapshots(base_commit["snapshot_id"], alt_commit["snapshot_id"])

    assert main_state["characters"]["Anna"]["status"] == "dead"
    assert alt_state["characters"]["Anna"]["status"] == "dead"
    assert alt_state["characters"]["Anna"]["last_location"] == "forest"
    assert "event_count" in diff
    assert vcs.list_branches()
    assert vcs.list_snapshots()


def test_event_sourcing_supports_merge_and_cherry_pick(tmp_path: Path) -> None:
    vcs = StoryVersionControl(
        event_store=EventStore(tmp_path / "events.jsonl"),
        snapshot_manager=SnapshotManager(tmp_path / "snapshots.json"),
        branch_manager=BranchManager(tmp_path / "branches.json"),
    )

    vcs.append_commit(
        title="Base scene",
        events=[_event(EventType.CHARACTER_APPEARS, "Anna", "Anna appears")],
        derived_state={},
    )
    vcs.create_branch("what-if")
    vcs.checkout("what-if")
    commit = vcs.append_commit(
        title="What if Anna survived",
        events=[
            _event(EventType.TRAVEL, "Anna", "Anna flees to the forest", location="forest"),
            _event(EventType.DISCOVERY, "Anna", "Anna discovers the hidden camp"),
        ],
        derived_state={},
    )

    vcs.checkout("main")
    cherry = vcs.cherry_pick("what-if", [commit["event_ids"][0]], target_branch="main")
    replay_after_pick = vcs.replay(branch="main")
    merge = vcs.merge_branch("what-if", target_branch="main")
    replay_after_merge = vcs.replay(branch="main")

    assert len(cherry["picked_event_ids"]) == 1
    assert replay_after_pick["characters"]["Anna"]["last_location"] == "forest"
    assert len(merge["merged_event_ids"]) == 1
    assert any("hidden camp" in item for item in replay_after_merge["knowledge"]["Anna"])


def test_event_replay_does_not_treat_scene_or_location_as_characters(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "events.jsonl")
    store.append_events([
        _event(EventType.SCENE_OPENS, "Smoke Scene 1", "Scene 'Smoke Scene 1' begins"),
        _event(EventType.WORLD_STATE_CHANGE, "castle", "Location 'castle' is established"),
        _event(EventType.CHARACTER_APPEARS, "Anna", "Anna appears in the scene"),
        _event(EventType.DISCOVERY, "Anna", "Anna discovers something", target="John"),
    ])

    state = store.replay_state()

    assert "Smoke Scene 1" not in state["characters"]
    assert "castle" not in state["characters"]
    assert "Anna" in state["characters"]
    assert "John" in state["characters"]


def test_relationship_graph_exposes_weighted_dimensions() -> None:
    graph = RelationshipGraph(FakeRelationshipRepo())
    graph.add_relationship("John", "Mira", RelationshipType.ALLY, strength=0.9)
    graph.add_relationship("John", "Drake", RelationshipType.ENEMY, strength=0.8)

    trust_edges = graph.query_by_dimension("trust", minimum=0.7)
    hatred_edges = graph.query_by_dimension("hatred", minimum=0.5)
    summary = graph.summary("John")

    assert len(trust_edges) == 1
    assert trust_edges[0].target == "Mira"
    assert len(hatred_edges) == 1
    assert hatred_edges[0].target == "Drake"
    assert summary["connections"] == 2
    assert "Mira" in summary["allies"]
    assert "Drake" in summary["enemies"]


def test_narrative_query_system_answers_knowledge_queries(tmp_path: Path) -> None:
    character_repo = FakeCharacterRepo([
        FakeCharacter(
            id="char-1",
            name="Lena",
            metadata_json={"memory": {"knowledge": ["knows about the dragon under the mountain"]}},
        ),
        FakeCharacter(
            id="char-2",
            name="Rook",
            metadata_json={"memory": {"beliefs": ["the dragon is waking"]}},
        ),
    ])
    graph = RelationshipGraph(FakeRelationshipRepo([
        FakeRelationship(id=1, source="Lena", target="Rook", relationship_type="ally", strength=0.8),
    ]))
    memory = NarrativeMemoryService(
        scene_repo=FakeListRepo([FakeScene(id="s1", title="Dragon Rumor", summary="Lena hears about the dragon")]),
        lore_repo=FakeListRepo([FakeLoreFact(key="dragon", value="The dragon sleeps under the mountain")]),
        character_repo=character_repo,
        timeline_repo=FakeListRepo([]),
        cache_path=tmp_path / "memory.json",
    )
    memory.rebuild_index()
    store = EventStore(tmp_path / "events.jsonl")

    query_system = NarrativeQuerySystem(
        character_repo=character_repo,
        lore_repo=FakeListRepo([FakeLoreFact(key="dragon", value="The dragon sleeps under the mountain")]),
        scene_repo=FakeListRepo([FakeScene(id="s1", title="Dragon Rumor")]),
        relationship_graph=graph,
        memory_service=memory,
        event_store=store,
    )

    answer = query_system.query("Who knows about the dragon?")
    relation = query_system.query("relationship between Lena and Rook")
    allied = query_system.query("Who is allied with Lena?")

    assert "Lena" in answer.answer
    assert "Rook" in answer.answer
    assert len(answer.evidence) == 2
    assert "ally" in relation.answer
    assert "Lena->Rook" in allied.answer


def test_narrative_query_system_understands_where_and_what_happened(tmp_path: Path) -> None:
    character_repo = FakeCharacterRepo([
        FakeCharacter(id="char-1", name="Anna", metadata_json={"memory": {"knowledge": ["saw the dragon"]}}),
    ])
    graph = RelationshipGraph(FakeRelationshipRepo())
    memory = NarrativeMemoryService(
        scene_repo=FakeListRepo([FakeScene(id="s1", title="Forest Escape")]),
        lore_repo=FakeListRepo([]),
        character_repo=character_repo,
        timeline_repo=FakeListRepo([]),
        cache_path=tmp_path / "memory.json",
    )
    memory.rebuild_index()
    store = EventStore(tmp_path / "events.jsonl")
    store.append_events([
        _event(EventType.TRAVEL, "Anna", "Anna flees to the forest", location="forest"),
        _event(EventType.DISCOVERY, "Anna", "Anna discovers the dragon cave"),
    ])

    query_system = NarrativeQuerySystem(
        character_repo=character_repo,
        lore_repo=FakeListRepo([]),
        scene_repo=FakeListRepo([FakeScene(id="s1", title="Forest Escape")]),
        relationship_graph=graph,
        memory_service=memory,
        event_store=store,
    )

    where_answer = query_system.query("Where is Anna?")
    what_answer = query_system.query("What happened to Anna?")

    assert "forest" in where_answer.answer
    assert "Anna flees to the forest" in what_answer.answer
    assert "Anna discovers the dragon cave" in what_answer.answer


def test_narrative_query_system_can_infer_location_from_scene_memory(tmp_path: Path) -> None:
    character_repo = FakeCharacterRepo([
        FakeCharacter(id="char-1", name="Anna"),
    ])
    graph = RelationshipGraph(FakeRelationshipRepo())
    memory = NarrativeMemoryService(
        scene_repo=FakeListRepo([
            FakeScene(
                id="s1",
                title="Escape",
                summary="Anna appears in the scene. Location 'forest' is established.",
            ),
        ]),
        lore_repo=FakeListRepo([]),
        character_repo=character_repo,
        timeline_repo=FakeListRepo([]),
        cache_path=tmp_path / "memory.json",
    )
    memory.rebuild_index()
    store = EventStore(tmp_path / "events.jsonl")
    store.append_events([
        _event(EventType.CHARACTER_APPEARS, "Anna", "Anna appears in the scene"),
    ])

    query_system = NarrativeQuerySystem(
        character_repo=character_repo,
        lore_repo=FakeListRepo([]),
        scene_repo=FakeListRepo([FakeScene(id="s1", title="Escape")]),
        relationship_graph=graph,
        memory_service=memory,
        event_store=store,
    )

    where_answer = query_system.query("Where is Anna?")

    assert "forest" in where_answer.answer.lower()


def test_narrative_query_system_routes_korean_character_profile_query(tmp_path: Path) -> None:
    character_repo = FakeCharacterRepo([
        FakeCharacter(
            id="char-1",
            name="홍윤재",
            metadata_json={
                "memory": {
                    "personality": ["충동적임"],
                    "trait_events": [
                        {
                            "trait": "unstable",
                            "surface": "미친",
                            "confidence": 0.9,
                            "source_scene": "초반 충돌",
                            "timestamp": "2025-01-01T00:00:00+00:00",
                        }
                    ],
                }
            },
        ),
    ])
    query_system = NarrativeQuerySystem(
        character_repo=character_repo,
        lore_repo=FakeListRepo([]),
        scene_repo=FakeListRepo([]),
        relationship_graph=RelationshipGraph(FakeRelationshipRepo()),
        memory_service=NarrativeMemoryService(
            scene_repo=FakeListRepo([]),
            lore_repo=FakeListRepo([]),
            character_repo=character_repo,
            timeline_repo=FakeListRepo([]),
            cache_path=tmp_path / "memory.json",
        ),
        event_store=EventStore(tmp_path / "events.jsonl"),
    )

    answer = query_system.query("홍윤재 어떤 사람이야?")

    assert "홍윤재" in answer.answer
    assert "unstable" in answer.answer


def test_narrative_memory_search_applies_korean_normalization(tmp_path: Path) -> None:
    character_repo = FakeCharacterRepo([
        FakeCharacter(id="char-1", name="준호", metadata_json={"memory": {"personality": ["성격이 이상한"]}}),
    ])
    memory = NarrativeMemoryService(
        scene_repo=FakeListRepo([
            FakeScene(id="s1", title="장면", summary="준호는 성격이 이상한 사람이다."),
        ]),
        lore_repo=FakeListRepo([]),
        character_repo=character_repo,
        timeline_repo=FakeListRepo([]),
        cache_path=tmp_path / "memory.json",
    )
    memory.rebuild_index()

    hits = memory.search_hierarchy("준호 미친 는 성격", character_name="준호", limit=3)

    assert hits
    assert any("성격" in hit.content for hit in hits)


def test_narrative_query_system_answers_korean_trait_who_query_from_character_memory(tmp_path: Path) -> None:
    character_repo = FakeCharacterRepo([
        FakeCharacter(
            id="char-1",
            name="현수",
            metadata_json={
                "memory": {
                    "trait_events": [
                        {
                            "trait": "funny",
                            "surface": "재밌",
                            "relation": "has_trait",
                            "confidence": 0.9,
                            "source_scene": "장면1",
                            "timestamp": "2026-01-01T00:00:00+00:00",
                        }
                    ],
                    "pending_trait_events": [
                        {
                            "trait": "provisional:재밌는",
                            "surface": "재밌는",
                            "relation": "has_trait",
                            "confidence": 0.46,
                            "source_scene": "장면2",
                            "timestamp": "2026-01-02T00:00:00+00:00",
                        }
                    ],
                }
            },
        ),
    ])
    query_system = NarrativeQuerySystem(
        character_repo=character_repo,
        lore_repo=FakeListRepo([
            FakeLoreFact(key="noise", value="completely unrelated lore text"),
        ]),
        scene_repo=FakeListRepo([]),
        relationship_graph=RelationshipGraph(FakeRelationshipRepo()),
        memory_service=NarrativeMemoryService(
            scene_repo=FakeListRepo([]),
            lore_repo=FakeListRepo([
                FakeLoreFact(key="noise", value="completely unrelated lore text"),
            ]),
            character_repo=character_repo,
            timeline_repo=FakeListRepo([]),
            cache_path=tmp_path / "memory.json",
        ),
        event_store=EventStore(tmp_path / "events.jsonl"),
    )

    answer = query_system.query("재밌는 사람 누구야?")

    assert "현수" in answer.answer
    assert answer.evidence
    assert answer.evidence[0]["character"] == "현수"
    assert answer.evidence[0]["matches"][0]["trait"] in {"funny", "provisional:재밌는"}


def test_narrative_query_system_answers_korean_trait_confirmation_query(tmp_path: Path) -> None:
    character_repo = FakeCharacterRepo([
        FakeCharacter(
            id="char-1",
            name="황링",
            metadata_json={
                "memory": {
                    "trait_events": [
                        {
                            "trait": "bad",
                            "surface": "나쁜",
                            "relation": "has_trait",
                            "confidence": 0.88,
                            "source_scene": "장면1",
                            "timestamp": "2026-01-01T00:00:00+00:00",
                        }
                    ]
                }
            },
        ),
    ])
    query_system = NarrativeQuerySystem(
        character_repo=character_repo,
        lore_repo=FakeListRepo([]),
        scene_repo=FakeListRepo([]),
        relationship_graph=RelationshipGraph(FakeRelationshipRepo()),
        memory_service=NarrativeMemoryService(
            scene_repo=FakeListRepo([]),
            lore_repo=FakeListRepo([]),
            character_repo=character_repo,
            timeline_repo=FakeListRepo([]),
            cache_path=tmp_path / "memory.json",
        ),
        event_store=EventStore(tmp_path / "events.jsonl"),
    )

    answer = query_system.query("황링은 나쁜 사람맞아?")

    assert "Yes" in answer.answer
    assert answer.evidence
    assert answer.evidence[0]["match_type"] == "permanent"
