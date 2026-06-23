from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from jose.jwt import UTC

from backend.consistency import (
    CharacterAgent,
    CriticAgent,
    LoreAgent,
    MultiAgentNarrativeAnalyzer,
    SemanticValidator,
    TimelineAgent,
)
from backend.llm.providers import create_llm_provider
from backend.narrative.analysis_cache import SceneAnalysisCache
from backend.narrative.character.memory_system import CharacterMemoryState
from backend.narrative.mutation.models import EventType, NarrativeEvent


class SceneAnalysisEnrichmentService:
    def __init__(self, cache: SceneAnalysisCache) -> None:
        self._cache = cache

    def get_cached(self, scene_hash: str) -> dict[str, Any] | None:
        return self._cache.get(scene_hash)

    def enrich_and_cache(
        self,
        scene_hash: str,
        scene_text: str,
        references: list[str],
        events: list[Any],
        character_names: list[str],
        character_memories: dict[str, Any],
        canon_conflicts: list[Any],
        drift_issues: list[Any],
        chronology_conflicts: list[str],
        flashback_count: int,
        flash_forward_count: int,
    ) -> dict[str, Any] | None:
        cached = self._cache.get(scene_hash)
        if cached is not None and cached.get("status") == "ready":
            return cached

        try:
            llm_provider = create_llm_provider()
        except Exception:
            return None

        semantic = SemanticValidator(llm_provider=llm_provider)
        agents = MultiAgentNarrativeAnalyzer(
            lore_agent=LoreAgent(llm_provider=llm_provider),
            character_agent=CharacterAgent(llm_provider=llm_provider),
            timeline_agent=TimelineAgent(llm_provider=llm_provider),
            critic_agent=CriticAgent(llm_provider=llm_provider),
        )

        semantic_result = semantic.validate(
            scene_text,
            references=references,
            events=events,
            character_memories=character_memories,
        )
        multi_agent_report = agents.analyze(
            scene_text,
            events=events,
            references=references,
            character_names=character_names,
            character_memories=character_memories,
            canon_conflicts=canon_conflicts,
            drift_issues=drift_issues,
            chronology_conflicts=chronology_conflicts,
            flashback_count=flashback_count,
            flash_forward_count=flash_forward_count,
            semantic_issues=semantic_result.issues,
        )

        payload = {
            "semantic_validation": _serialize_semantic_result(semantic_result),
            "multi_agent_analysis": multi_agent_report.as_dict(),
            "status": "ready",
        }
        self._cache.set(scene_hash, payload)
        return payload

    def build_job_payload(
        self,
        scene_hash: str,
        scene_text: str,
        references: list[str],
        events: list[Any],
        character_names: list[str],
        character_memories: dict[str, Any],
        canon_conflicts: list[Any],
        drift_issues: list[Any],
        chronology_conflicts: list[str],
        flashback_count: int,
        flash_forward_count: int,
    ) -> dict[str, Any]:
        return {
            "scene_hash": scene_hash,
            "scene_text": scene_text,
            "references": list(references),
            "events": [_serialize_event(item) for item in events],
            "character_names": list(character_names),
            "character_memories": {
                name: _serialize_memory(memory)
                for name, memory in character_memories.items()
            },
            "canon_conflicts": [_serialize_conflict(item) for item in canon_conflicts],
            "drift_issues": [_serialize_drift_issue(item) for item in drift_issues],
            "chronology_conflicts": list(chronology_conflicts),
            "flashback_count": int(flashback_count),
            "flash_forward_count": int(flash_forward_count),
            "status": "pending",
        }

    def enrich_from_job(self, job_payload: dict[str, Any]) -> dict[str, Any] | None:
        return self.enrich_and_cache(
            scene_hash=str(job_payload["scene_hash"]),
            scene_text=str(job_payload["scene_text"]),
            references=[str(item) for item in job_payload.get("references", [])],
            events=[_deserialize_event(item) for item in job_payload.get("events", [])],
            character_names=[str(item) for item in job_payload.get("character_names", [])],
            character_memories={
                str(name): _deserialize_memory(memory)
                for name, memory in (job_payload.get("character_memories") or {}).items()
            },
            canon_conflicts=[SimpleNamespace(**item) for item in job_payload.get("canon_conflicts", [])],
            drift_issues=[SimpleNamespace(**item) for item in job_payload.get("drift_issues", [])],
            chronology_conflicts=[str(item) for item in job_payload.get("chronology_conflicts", [])],
            flashback_count=int(job_payload.get("flashback_count") or 0),
            flash_forward_count=int(job_payload.get("flash_forward_count") or 0),
        )


def _serialize_semantic_result(result: Any) -> dict[str, Any]:
    return {
        "score": result.score,
        "provider_used": result.provider_used,
        "notes": result.notes,
        "issues": [
            {
                "rule_id": issue.rule_id,
                "category": issue.category,
                "severity": issue.severity,
                "message": issue.message,
                "evidence": issue.evidence,
                "entities": issue.entities,
                "source": issue.source,
            }
            for issue in result.issues
        ],
    }


def _serialize_event(event: Any) -> dict[str, Any]:
    event_type = getattr(getattr(event, "event_type", None), "value", getattr(event, "event_type", ""))
    timestamp = getattr(event, "timestamp", None)
    timestamp_value = timestamp.isoformat() if hasattr(timestamp, "isoformat") else None
    return {
        "event_type": str(event_type),
        "subject": str(getattr(event, "subject", "")),
        "predicate": str(getattr(event, "predicate", "")),
        "target": getattr(event, "target", None),
        "action": getattr(event, "action", None),
        "location": getattr(event, "location", None),
        "attributes": dict(getattr(event, "attributes", {}) or {}),
        "timestamp": timestamp_value,
        "source_scene": getattr(event, "source_scene", None),
        "is_flashback": bool(getattr(event, "is_flashback", False)),
    }


def _deserialize_event(payload: dict[str, Any]) -> NarrativeEvent:
    timestamp_raw = payload.get("timestamp")
    timestamp = datetime.fromisoformat(timestamp_raw) if timestamp_raw else datetime.now(UTC)
    return NarrativeEvent(
        event_type=EventType(str(payload.get("event_type") or EventType.TIMELINE_BEAT.value)),
        subject=str(payload.get("subject") or ""),
        predicate=str(payload.get("predicate") or ""),
        target=payload.get("target"),
        action=payload.get("action"),
        location=payload.get("location"),
        attributes=dict(payload.get("attributes") or {}),
        timestamp=timestamp,
        source_scene=payload.get("source_scene"),
        is_flashback=bool(payload.get("is_flashback", False)),
    )


def _serialize_memory(memory: Any) -> dict[str, list[str]]:
    if hasattr(memory, "as_dict"):
        return memory.as_dict()
    return {
        "personality": list(getattr(memory, "personality", []) or []),
        "beliefs": list(getattr(memory, "beliefs", []) or []),
        "knowledge": list(getattr(memory, "knowledge", []) or []),
        "desires": list(getattr(memory, "desires", []) or []),
    }


def _deserialize_memory(payload: dict[str, Any]) -> CharacterMemoryState:
    return CharacterMemoryState(
        personality=list(payload.get("personality", []) or []),
        beliefs=list(payload.get("beliefs", []) or []),
        knowledge=list(payload.get("knowledge", []) or []),
        desires=list(payload.get("desires", []) or []),
    )


def _serialize_conflict(conflict: Any) -> dict[str, Any]:
    return {
        "rule_id": str(getattr(conflict, "rule_id", "")),
        "message": str(getattr(conflict, "message", "")),
        "severity": str(getattr(conflict, "severity", "warning")),
        "entities": list(getattr(conflict, "entities", []) or []),
    }


def _serialize_drift_issue(issue: Any) -> dict[str, Any]:
    return {
        "rule_id": str(getattr(issue, "rule_id", "")),
        "severity": str(getattr(issue, "severity", "warning")),
        "character": str(getattr(issue, "character", "")),
        "message": str(getattr(issue, "message", "")),
        "evidence": list(getattr(issue, "evidence", []) or []),
    }