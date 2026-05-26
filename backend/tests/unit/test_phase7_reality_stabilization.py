from __future__ import annotations

from pathlib import Path

from backend.narrative.mutation.models import EventType, NarrativeEvent
from backend.narrative.reality import EntityRegistry, EntityType, TypedEvent, validate_typed_event
from backend.narrative.state_engine import NarrativeStateMutationEngine
from backend.tests.unit.test_phase4_ai_intelligence import (
    FakeCanonRepo,
    FakeCharacter,
    FakeCharacterRepo,
    FakeLoreFact,
    FakeLoreRepo,
    FakeRelationshipRepo,
    FakeSceneRepo,
    FakeTimelineRepo,
)
from backend.version_control import BranchManager, EventStore, SnapshotManager, StoryVersionControl


def _event(event_type: EventType, subject: str, predicate: str, **kwargs) -> NarrativeEvent:
    return NarrativeEvent(event_type=event_type, subject=subject, predicate=predicate, **kwargs)


def test_typed_ontology_registry_and_validation() -> None:
    registry = EntityRegistry()
    registry.register("Anna", EntityType.CHARACTER, event_id="evt-1")
    registry.register("Castle", EntityType.LOCATION, event_id="evt-2")

    typed_event = TypedEvent(
        event_id="evt-3",
        event_type="murder",
        subject="John",
        subject_type=EntityType.CHARACTER,
        predicate="John kills Anna",
        target="Anna",
        target_type=EntityType.CHARACTER,
        location="castle",
    )

    errors = validate_typed_event(typed_event)
    payload = registry.as_payload()

    assert errors == []
    assert payload["counts"]["character"] == 1
    assert payload["counts"]["location"] == 1


def test_story_vcs_replay_determinism_and_snapshot_integrity(tmp_path: Path) -> None:
    vcs = StoryVersionControl(
        event_store=EventStore(tmp_path / "events.jsonl"),
        snapshot_manager=SnapshotManager(tmp_path / "snapshots.json"),
        branch_manager=BranchManager(tmp_path / "branches.json"),
    )

    commit = vcs.append_commit(
        title="Determinism setup",
        events=[
            _event(EventType.CHARACTER_APPEARS, "Anna", "Anna appears"),
            _event(EventType.TRAVEL, "Anna", "Anna moves to the forest", location="forest"),
            _event(EventType.DISCOVERY, "Anna", "Anna discovers an oath"),
        ],
        derived_state={},
    )

    replay_report = vcs.replay_determinism_report("main")
    snapshot_report = vcs.verify_snapshot_integrity(commit["snapshot_id"])
    branch_report = vcs.verify_branch_replay("main")

    assert replay_report["deterministic"] is True
    assert isinstance(commit["derived_state_checksum"], str) and len(commit["derived_state_checksum"]) == 64
    assert snapshot_report["valid"] is True
    assert branch_report["valid"] is True


def test_state_engine_emits_phase7_reality_payloads(tmp_path: Path) -> None:
    repositories = {
        "canon": FakeCanonRepo(),
        "character": FakeCharacterRepo([
            FakeCharacter(id="char-john", name="John"),
            FakeCharacter(id="char-anna", name="Anna"),
        ]),
        "lore": FakeLoreRepo([FakeLoreFact(key="oath", value="Betrayal is forbidden")]),
        "relationship": FakeRelationshipRepo(),
        "scene": FakeSceneRepo(),
        "timeline": FakeTimelineRepo(),
    }

    engine = NarrativeStateMutationEngine(repositories, llm_provider=None)
    engine._event_store._file_path = tmp_path / "events.jsonl"
    engine._vcs.snapshots._file_path = tmp_path / "snapshots.json"
    engine._vcs.branches._file_path = tmp_path / "branches.json"
    engine._knowledge_graph._file_path = tmp_path / "kg.json"

    result = engine.process_scene(
        "John killed Anna in the castle. Later John formed an alliance with Mira.",
        {"scene_title": "Phase7 Demo", "branch": "main"},
    )

    assert result["success"] is True
    assert "ontology" in result
    assert "entity_registry" in result["ontology"]
    assert isinstance(result["ontology"]["typed_events"], list)
    assert "reasoning" in result
    assert "evidence_chains" in result["reasoning"]
    assert "knowledge_graph" in result
    assert "summary" in result["knowledge_graph"]
    assert "replay_determinism" in result["event_sourcing"]
    assert "snapshot_integrity" in result["version_control"]
