from __future__ import annotations

from pathlib import Path
from time import sleep

from backend.llm.providers.base import BaseLLMProvider, LLMMessage, LLMResponse
from backend.narrative.analysis_cache import SceneAnalysisCache, build_scene_analysis_hash
from backend.narrative.analysis_enrichment import SceneAnalysisEnrichmentService
from backend.narrative.analysis_queue import SceneAnalysisQueue
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


class FakeLLMProvider(BaseLLMProvider):
    name = "fake-llm"

    def complete(self, messages: list[LLMMessage], **kwargs):
        system_prompt = messages[0].content.lower()
        if "semantic narrative validator" in system_prompt:
            return LLMResponse(
                content='[{"category":"unnatural_progression","severity":"warning","message":"LLM sees abrupt escalation.","evidence":["murder -> alliance"],"entities":["John","Mira"]}]'
            )
        if "canon-focused" in system_prompt:
            return LLMResponse(content="- canon remains stable")
        if "personality-focused" in system_prompt:
            return LLMResponse(content="- motivation needs reinforcement")
        if "timeline-focused" in system_prompt:
            return LLMResponse(content="- chronology remains readable")
        if "pacing critic" in system_prompt:
            return LLMResponse(content="- abrupt tonal transition after murder")
        return LLMResponse(content="[]")


def _build_engine(tmp_path: Path) -> NarrativeStateMutationEngine:
    repositories = {
        "canon": FakeCanonRepo(),
        "character": FakeCharacterRepo([
            FakeCharacter(id="char-john", name="John"),
            FakeCharacter(id="char-anna", name="Anna"),
            FakeCharacter(id="char-mira", name="Mira"),
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
    engine._analysis_cache = SceneAnalysisCache(
        tmp_path / "scene_analysis_cache.json",
        ttl_seconds=3600,
        policy_signature="test-policy",
    )
    engine._analysis_queue = SceneAnalysisQueue(tmp_path / "scene_analysis_jobs")
    engine._analysis_enrichment = SceneAnalysisEnrichmentService(engine._analysis_cache)
    return engine


def test_scene_analysis_cache_round_trip(tmp_path: Path) -> None:
    cache = SceneAnalysisCache(tmp_path / "scene-analysis.json", ttl_seconds=3600, policy_signature="policy-a")
    scene_hash = build_scene_analysis_hash("John enters.", "Scene A", "main", ["castle"])

    cache.set(scene_hash, {"status": "ready", "semantic_validation": {"score": 0.8}})

    assert cache.has(scene_hash) is True
    assert cache.get(scene_hash) == {"status": "ready", "semantic_validation": {"score": 0.8}}


def test_scene_analysis_cache_expires_and_invalidates_on_policy_change(tmp_path: Path) -> None:
    scene_hash = build_scene_analysis_hash("John enters.", "Scene A", "main", ["castle"])
    cache = SceneAnalysisCache(tmp_path / "scene-analysis.json", ttl_seconds=1, policy_signature="policy-a")
    cache.set(scene_hash, {"status": "ready"})

    assert cache.get(scene_hash) == {"status": "ready"}
    sleep(2)
    assert cache.get(scene_hash) is None

    cache = SceneAnalysisCache(tmp_path / "scene-analysis.json", ttl_seconds=3600, policy_signature="policy-a")
    cache.set(scene_hash, {"status": "ready"})
    other_policy_cache = SceneAnalysisCache(tmp_path / "scene-analysis.json", ttl_seconds=3600, policy_signature="policy-b")
    assert other_policy_cache.get(scene_hash) is None


def test_process_scene_returns_pending_fast_path_and_enqueues_worker_job(tmp_path: Path) -> None:
    engine = _build_engine(tmp_path)

    result = engine.process_scene(
        "John killed Anna, then formed an alliance with Mira.",
        {"scene_title": "Async Demo", "branch": "main"},
    )

    assert result["analysis_enrichment"]["status"] == "pending"
    assert result["analysis_enrichment"]["cache_hit"] is False
    assert engine._analysis_queue.has_inflight(result["analysis_enrichment"]["scene_hash"]) is True


def test_process_scene_does_not_reschedule_when_enrichment_is_already_pending(tmp_path: Path) -> None:
    engine = _build_engine(tmp_path)

    first = engine.process_scene(
        "John killed Anna, then formed an alliance with Mira.",
        {"scene_title": "Pending Demo", "branch": "main"},
    )
    second = engine.process_scene(
        "John killed Anna, then formed an alliance with Mira.",
        {"scene_title": "Pending Demo", "branch": "main"},
    )

    assert first["analysis_enrichment"]["status"] == "pending"
    assert second["analysis_enrichment"]["status"] == "pending"
    pending_jobs = list((tmp_path / "scene_analysis_jobs" / "pending").glob("*.json"))
    assert len(pending_jobs) == 1


def test_process_scene_uses_cached_enrichment_when_scene_hash_repeats(tmp_path: Path, monkeypatch) -> None:
    engine = _build_engine(tmp_path)
    monkeypatch.setattr("backend.narrative.analysis_enrichment.create_llm_provider", lambda: FakeLLMProvider())

    scene_text = "John killed Anna, then formed an alliance with Mira."
    first = engine.process_scene(
        scene_text,
        {"scene_title": "Cache Demo", "branch": "main", "async_analysis": False},
    )
    second = engine.process_scene(
        scene_text,
        {"scene_title": "Cache Demo", "branch": "main", "async_analysis": True},
    )

    assert first["analysis_enrichment"]["status"] == "ready"
    assert first["semantic_validation"]["provider_used"] == "fake-llm"
    assert second["analysis_enrichment"]["status"] == "cached"
    assert second["analysis_enrichment"]["cache_hit"] is True
    assert second["semantic_validation"]["provider_used"] == "fake-llm"
    assert second["multi_agent_analysis"]["structured_summary"]


def test_queue_worker_job_can_fill_cache_for_later_request(tmp_path: Path, monkeypatch) -> None:
    engine = _build_engine(tmp_path)
    monkeypatch.setattr("backend.narrative.analysis_enrichment.create_llm_provider", lambda: FakeLLMProvider())

    initial = engine.process_scene(
        "John killed Anna, then formed an alliance with Mira.",
        {"scene_title": "Worker Demo", "branch": "main"},
    )
    claimed = engine._analysis_queue.claim_next()
    assert claimed is not None
    processing_path, job_payload = claimed

    engine._analysis_enrichment.enrich_from_job(job_payload)
    engine._analysis_queue.complete(processing_path)

    repeated = engine.process_scene(
        "John killed Anna, then formed an alliance with Mira.",
        {"scene_title": "Worker Demo", "branch": "main"},
    )

    assert initial["analysis_enrichment"]["status"] == "pending"
    assert repeated["analysis_enrichment"]["status"] == "cached"
    assert repeated["semantic_validation"]["provider_used"] == "fake-llm"