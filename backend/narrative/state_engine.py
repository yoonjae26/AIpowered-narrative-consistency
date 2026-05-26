"""
Narrative State Mutation Engine
Pipeline: Scene Input -> Entity Extraction -> Event Generation ->
          State Mutation -> Persistence -> Timeline -> Consistency Check
"""
from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from backend.consistency import (
    CharacterAgent,
    CriticAgent,
    LoreAgent,
    MultiAgentNarrativeAnalyzer,
    SemanticValidator,
    TimelineAgent,
)
from backend.database.repositories.canon_repository import CanonRepository
from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.relationship_repository import RelationshipRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.database.repositories.timeline_repository import TimelineRepository
from backend.llm.providers.base import BaseLLMProvider
from backend.narrative.character import CharacterMemorySystem, SemanticCharacterDriftDetector
from backend.narrative.mutation import (
    ConsistencyChecker,
    EntityExtractor,
    EventGenerator,
    StateMutator,
)
from backend.narrative.reality import (
    EntityRegistry,
    EntityType,
    ExplainableReasoningEngine,
    NarrativeKnowledgeGraph,
    TypedEvent,
    relationship_edge_for_event,
    validate_typed_event,
)
from backend.narrative.query_system import NarrativeQuerySystem
from backend.narrative.relationships.graph import RelationshipGraph
from backend.narrative.timeline import TimelineEngine
from backend.narrative.warnings import WarningGenerator
from backend.narrative.world import CanonProtectionLayer, CanonRegistry, LoreManager
from backend.observability.langfuse_client import LangfuseClient
from backend.observability.metrics import compute_consistency_metrics, metrics
from backend.observability.structured_logger import get_logger
from backend.rag import NarrativeMemoryService
from backend.version_control import EventStore, StoryVersionControl

logger = logging.getLogger(__name__)


class NarrativeStateMutationEngine:
    """
    Orchestrates the full mutation pipeline given a raw scene text.

    Args:
        repositories: dict with keys 'character', 'scene', 'timeline', 'relationship'.
        llm_provider: optional BaseLLMProvider; None = heuristic-only mode.
        canon_rules: optional dict e.g. {'resurrection_forbidden': True}
    """

    def __init__(
        self,
        repositories: dict[str, Any],
        llm_provider: BaseLLMProvider | None = None,
        canon_rules: dict | None = None,
    ) -> None:
        canon_repo: CanonRepository | None    = repositories.get("canon")
        char_repo: CharacterRepository    = repositories["character"]
        lore_repo: LoreRepository | None      = repositories.get("lore")
        scene_repo: SceneRepository       = repositories["scene"]
        timeline_repo: TimelineRepository = repositories["timeline"]
        rel_repo: RelationshipRepository  = repositories["relationship"]

        self._extractor = EntityExtractor(
            llm_provider=llm_provider,
            character_repo=char_repo,
        )
        self._generator   = EventGenerator(llm_provider=llm_provider)
        self._mutator     = StateMutator(char_repo, scene_repo, timeline_repo, rel_repo)
        self._checker     = ConsistencyChecker(char_repo, rel_repo, canon_rules=canon_rules)
        self._timeline    = TimelineEngine()
        self._warn_gen    = WarningGenerator()
        self._memory      = NarrativeMemoryService(scene_repo, lore_repo, char_repo, timeline_repo)
        self._char_memory = CharacterMemorySystem(char_repo)
        self._drift       = SemanticCharacterDriftDetector()
        self._event_store = EventStore()
        self._vcs         = StoryVersionControl(event_store=self._event_store)
        self._graph       = RelationshipGraph(rel_repo)
        self._canon_layer = CanonProtectionLayer(
            canon_registry=CanonRegistry(canon_repo) if canon_repo is not None else None,
            lore_manager=LoreManager(lore_repo) if lore_repo is not None else None,
        )
        self._semantic    = SemanticValidator(llm_provider=llm_provider)
        self._agents      = MultiAgentNarrativeAnalyzer(
            lore_agent=LoreAgent(llm_provider=llm_provider),
            character_agent=CharacterAgent(llm_provider=llm_provider),
            timeline_agent=TimelineAgent(llm_provider=llm_provider),
            critic_agent=CriticAgent(llm_provider=llm_provider),
        )
        self._query       = NarrativeQuerySystem(
            character_repo=char_repo,
            lore_repo=lore_repo,
            scene_repo=scene_repo,
            relationship_graph=self._graph,
            memory_service=self._memory,
            event_store=self._event_store,
        )
        self._reasoning = ExplainableReasoningEngine()
        self._knowledge_graph = NarrativeKnowledgeGraph()
        self._langfuse = LangfuseClient()
        self._obs_logger = get_logger("backend.observability.pipeline")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_scene(
        self,
        scene_text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run the full pipeline. Never raises -- errors are captured in the result.
        """
        context = context or {}
        allow_canon_override = bool(context.get("allow_canon_override", False))
        branch_name = str(context.get("branch") or self._vcs.current_branch())
        scene_title: str | None = context.get("scene_title") or context.get("title")
        canon_rules: dict = context.get("canon_rules") or {}

        # Allow per-call canon rule override
        if canon_rules:
            self._checker._canon = canon_rules
        if branch_name != self._vcs.current_branch():
            self._vcs.checkout(branch_name)

        started_at = perf_counter()
        trace = self._langfuse.start_trace(
            name="narrative.process_scene",
            input_payload={
                "scene_title": scene_title,
                "scene_length": len(scene_text),
                "branch": branch_name,
                "allow_canon_override": allow_canon_override,
            },
            metadata={"pipeline": "state-mutation", "phase": "phase6"},
        )

        try:
            # 1. Entity Extraction
            logger.info("Pipeline[1]: extracting entities (scene=%s)", scene_title)
            entities = self._extractor.extract(scene_text)

            # 2. Event Generation
            logger.info("Pipeline[2]: generating events (%d chars, %d locs, %d actions)",
                        len(entities.characters), len(entities.locations), len(entities.actions))
            events = self._generator.generate(scene_text, entities, scene_title=scene_title)

            # 3+4. State Mutation + Persistence
            logger.info("Pipeline[3]: applying %d events", len(events))
            mutation_result = self._mutator.apply(events, scene_title=scene_title)

            logger.info("Pipeline[3.5]: updating character memory")
            character_memories = self._char_memory.update_from_events(events)

            # 5. Timeline
            logger.info("Pipeline[4]: building timeline")
            timeline_entries, chrono_report = self._timeline.process(events, scene_text)

            logger.info("Pipeline[4.5]: syncing narrative memory")
            self._memory.sync_after_mutation(
                scene_title=scene_title,
                character_names=list(character_memories.keys()),
                events=events,
            )
            memory_context = self._memory.build_context(
                " ".join([scene_text, scene_title or "", " ".join(e.subject for e in events)]).strip(),
                limit=int(context.get("memory_limit", 8)),
            )
            semantic_references = [
                item["content"]
                for bucket in memory_context.values()
                for item in bucket
                if isinstance(item, dict) and "content" in item
            ]

            logger.info("Pipeline[4.6]: drift + canon checks")
            drift_issues = self._drift.detect(events, character_memories)
            canon_conflicts = self._canon_layer.check_events(events, allow_override=allow_canon_override)
            semantic_result = self._semantic.validate(
                scene_text,
                references=semantic_references,
                events=events,
                character_memories=character_memories,
            )

            logger.info("Pipeline[4.7]: event sourcing + version control")
            commit_result = self._vcs.append_commit(
                title=scene_title or "Scene commit",
                events=events,
                derived_state={},
            )

            typed_events = _build_typed_events(events=events, event_ids=commit_result["event_ids"])
            ontology_registry, ontology_errors, typed_relationships = _build_ontology_projection(
                entities=entities,
                typed_events=typed_events,
            )
            self._knowledge_graph.integrate_scene(
                typed_events=[
                    {
                        "event_id": item.event_id,
                        "event_type": item.event_type,
                        "subject": item.subject,
                        "subject_type": item.subject_type.value,
                        "predicate": item.predicate,
                        "target": item.target,
                        "target_type": item.target_type.value if item.target_type is not None else None,
                        "location": item.location,
                        "happened_at": str(getattr(events[index], "timestamp", "")) if index < len(events) else "",
                    }
                    for index, item in enumerate(typed_events)
                ],
                scene_title=scene_title,
            )

            # 6. Consistency Check
            logger.info("Pipeline[5]: running consistency checks")
            consistency_report = self._checker.check(mutation_result, events, scene_text)
            semantic_warnings = [issue.message for issue in semantic_result.issues if issue.severity != "error"]
            semantic_errors = [issue.message for issue in semantic_result.issues if issue.severity == "error"]
            multi_agent_report = self._agents.analyze(
                scene_text,
                events=events,
                references=semantic_references,
                character_names=[entity.name for entity in entities.characters],
                character_memories=character_memories,
                canon_conflicts=canon_conflicts,
                drift_issues=drift_issues,
                chronology_conflicts=chrono_report.conflicts,
                flashback_count=len(chrono_report.flashbacks),
                flash_forward_count=len(chrono_report.flash_forwards),
                semantic_issues=semantic_result.issues,
            )
            explainability = self._reasoning.build(
                semantic_issues=semantic_result.issues,
                drift_issues=drift_issues,
                canon_conflicts=canon_conflicts,
                chronology_conflicts=chrono_report.conflicts,
                multi_agent_report=multi_agent_report,
            )

            # 7. Collect all warnings
            all_warnings = self._warn_gen.from_consistency_report(
                consistency_report.warnings + semantic_warnings,
                consistency_report.errors + semantic_errors,
                scene=scene_title,
            ) + self._warn_gen.from_timeline_report(
                chrono_report.conflicts,
                scene=scene_title,
            )
            all_warnings.extend(
                self._warn_gen.make(
                    issue.rule_id,
                    entities=[issue.character],
                    scene=scene_title,
                )
                for issue in drift_issues
            )
            all_warnings.extend(
                self._warn_gen.make(
                    conflict.rule_id,
                    entities=conflict.entities,
                    scene=scene_title,
                )
                for conflict in canon_conflicts
            )
            all_warnings.extend(
                self._warn_gen.make(
                    issue.rule_id,
                    entities=issue.entities,
                    scene=scene_title,
                )
                for issue in semantic_result.issues
            )

            success_payload: dict[str, Any] = {
                "success": True,
                "scene_title": scene_title,
                "entities": {
                    "characters": [_entity_dict(e) for e in entities.characters],
                    "locations":  [_entity_dict(e) for e in entities.locations],
                    "objects":    [_entity_dict(e) for e in entities.objects],
                    "concepts":   [_entity_dict(e) for e in entities.concepts],
                    "actions":    [_action_dict(a) for a in entities.actions],
                },
                "events": [_event_dict(e) for e in events],
                "mutation": {
                    "scene_id": mutation_result.scene_id,
                    "characters_upserted": mutation_result.characters_upserted,
                    "timeline_events_created": mutation_result.timeline_events_created,
                    "events_applied_count": len(mutation_result.events_applied),
                },
                "event_sourcing": {
                    "branch": commit_result["branch"],
                    "event_ids": commit_result["event_ids"],
                    "derived_state": commit_result["derived_state"],
                    "derived_state_checksum": commit_result["derived_state_checksum"],
                    "replay_determinism": self._vcs.replay_determinism_report(branch=commit_result["branch"]),
                    "branch_replay_verification": self._vcs.verify_branch_replay(branch=commit_result["branch"]),
                },
                "version_control": {
                    "snapshot_id": commit_result["snapshot_id"],
                    "branch": commit_result["branch"],
                    "snapshot_integrity": self._vcs.verify_snapshot_integrity(commit_result["snapshot_id"]),
                },
                "ontology": {
                    "entity_registry": ontology_registry.as_payload(),
                    "typed_events": [
                        {
                            "event_id": item.event_id,
                            "event_type": item.event_type,
                            "subject": item.subject,
                            "subject_type": item.subject_type.value,
                            "predicate": item.predicate,
                            "target": item.target,
                            "target_type": item.target_type.value if item.target_type is not None else None,
                            "location": item.location,
                            "attributes": item.attributes,
                        }
                        for item in typed_events
                    ],
                    "typed_relationship_edges": [
                        {
                            "source": edge.source,
                            "target": edge.target,
                            "edge_type": edge.edge_type,
                            "weight": edge.weight,
                            "evidence_event_ids": edge.evidence_event_ids,
                        }
                        for edge in typed_relationships
                    ],
                    "validation_errors": ontology_errors,
                },
                "reasoning": explainability,
                "knowledge_graph": {
                    "summary": self._knowledge_graph.summary(),
                },
                "memory": {
                    "retrieved": memory_context,
                    "character_state": {
                        name: memory.as_dict()
                        for name, memory in character_memories.items()
                    },
                },
                "timeline": {
                    "valid": chrono_report.valid,
                    "flashback_count": len(chrono_report.flashbacks),
                    "flash_forward_count": len(chrono_report.flash_forwards),
                    "conflicts": chrono_report.conflicts,
                    "entries_count": len(timeline_entries),
                },
                "drift": {
                    "issues": [
                        {
                            "rule_id": issue.rule_id,
                            "severity": issue.severity,
                            "character": issue.character,
                            "message": issue.message,
                            "evidence": issue.evidence,
                        }
                        for issue in drift_issues
                    ],
                },
                "semantic_validation": {
                    "score": semantic_result.score,
                    "provider_used": semantic_result.provider_used,
                    "notes": semantic_result.notes,
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
                        for issue in semantic_result.issues
                    ],
                },
                "multi_agent_analysis": multi_agent_report.as_dict(),
                "canon_protection": {
                    "conflicts": [
                        {
                            "rule_id": conflict.rule_id,
                            "severity": conflict.severity,
                            "message": conflict.message,
                            "entities": conflict.entities,
                        }
                        for conflict in canon_conflicts
                    ],
                    "allow_override": allow_canon_override,
                },
                "consistency": {
                    "consistent": consistency_report.consistent,
                    "warnings": consistency_report.warnings + semantic_warnings,
                    "errors": consistency_report.errors + semantic_errors + [conflict.message for conflict in canon_conflicts if conflict.severity == "error"],
                },
                "writer_warnings": [
                    {
                        "rule_id": w.rule_id,
                        "severity": w.severity.value,
                        "message": w.message,
                        "suggestion": w.suggestion,
                        "entities": w.entities_involved,
                        "formatted": w.format(),
                    }
                    for w in all_warnings
                ],
            }

            consistency_metrics = compute_consistency_metrics(success_payload)
            success_payload["consistency_metrics"] = consistency_metrics.as_dict()

            latency = perf_counter() - started_at
            metrics.observe("pipeline.process_scene.latency_seconds", latency)
            metrics.increment("pipeline.process_scene.success", 1)
            metrics.set_gauge("consistency.timeline_accuracy", consistency_metrics.timeline_accuracy)
            metrics.set_gauge("consistency.character_consistency", consistency_metrics.character_consistency)
            metrics.set_gauge("consistency.canon_integrity", consistency_metrics.canon_integrity)
            metrics.set_gauge("consistency.overall", consistency_metrics.overall_consistency)

            self._obs_logger.info(
                "process_scene_completed",
                extra={
                    "scene_title": scene_title,
                    "branch": branch_name,
                    "events_count": len(events),
                    "warnings_count": len(success_payload["writer_warnings"]),
                    "consistency_metrics": consistency_metrics.as_dict(),
                    "latency_seconds": latency,
                },
            )
            self._langfuse.record_span(
                trace,
                name="pipeline.summary",
                input_payload={"scene_title": scene_title, "branch": branch_name},
                output_payload={
                    "events_count": len(events),
                    "warnings_count": len(success_payload["writer_warnings"]),
                    "consistency_metrics": consistency_metrics.as_dict(),
                },
            )
            self._langfuse.finish_trace(
                trace,
                output_payload={
                    "success": True,
                    "events_count": len(events),
                    "overall_consistency": consistency_metrics.overall_consistency,
                    "latency_seconds": latency,
                },
            )

            return success_payload

        except Exception as exc:
            latency = perf_counter() - started_at
            metrics.observe("pipeline.process_scene.latency_seconds", latency)
            metrics.increment("pipeline.process_scene.failure", 1)
            self._langfuse.finish_trace(
                trace,
                output_payload={
                    "success": False,
                    "error": str(exc),
                    "latency_seconds": latency,
                },
                level="ERROR",
            )
            logger.error("Mutation pipeline failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc), "scene_title": scene_title}

    def create_branch(self, name: str, from_branch: str | None = None) -> dict[str, Any]:
        return self._vcs.create_branch(name, from_branch=from_branch)

    def merge_branch(self, source_branch: str, target_branch: str | None = None) -> dict[str, Any] | None:
        return self._vcs.merge_branch(source_branch, target_branch=target_branch)

    def cherry_pick(self, source_branch: str, event_ids: list[str], target_branch: str | None = None) -> dict[str, Any] | None:
        return self._vcs.cherry_pick(source_branch, event_ids=event_ids, target_branch=target_branch)

    def checkout_branch(self, name: str) -> dict[str, Any] | None:
        return self._vcs.checkout(name)

    def list_branches(self) -> list[dict[str, Any]]:
        return self._vcs.list_branches()

    def list_snapshots(self) -> list[dict[str, Any]]:
        return self._vcs.list_snapshots()

    def diff_snapshots(self, snapshot_a: str, snapshot_b: str) -> str:
        return self._vcs.diff_snapshots(snapshot_a, snapshot_b)

    def rollback_to_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        return self._vcs.rollback(snapshot_id)

    def replay_branch(self, branch: str | None = None, to_event_id: str | None = None) -> dict[str, Any]:
        return self._vcs.replay(branch=branch, to_event_id=to_event_id)

    def replay_determinism(self, branch: str | None = None) -> dict[str, Any]:
        return self._vcs.replay_determinism_report(branch=branch)

    def verify_branch_replay(self, branch: str | None = None) -> dict[str, Any]:
        return self._vcs.verify_branch_replay(branch=branch)

    def verify_snapshot_integrity(self, snapshot_id: str) -> dict[str, Any]:
        return self._vcs.verify_snapshot_integrity(snapshot_id)

    def query(self, query_text: str) -> dict[str, Any]:
        answer = self._query.query(query_text)
        return {
            "query": answer.query,
            "answer": answer.answer,
            "evidence": answer.evidence,
        }

    def relationship_summary(self, character_id: str) -> dict[str, Any]:
        return self._graph.summary(character_id)

    def relationship_dimension(self, dimension: str, minimum: float = 0.5) -> list[dict[str, Any]]:
        return [
            {
                "source": edge.source,
                "target": edge.target,
                "relationship_type": edge.relationship_type.value,
                "strength": edge.strength,
                "dimensions": edge.dimensions,
            }
            for edge in self._graph.query_by_dimension(dimension, minimum=minimum)
        ]

    def knowledge_graph_summary(self) -> dict[str, Any]:
        return self._knowledge_graph.summary()

    def knowledge_graph_traverse(self, node_id: str, depth: int = 1) -> dict[str, Any]:
        return self._knowledge_graph.traverse(node_id=node_id, depth=depth)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _entity_dict(e: Any) -> dict:
    return {
        "name": e.name,
        "entity_type": e.entity_type,
        "attributes": e.attributes,
        "confidence": e.confidence,
        "canonical_name": e.canonical_name,
        "db_id": e.db_id,
    }


def _action_dict(a: Any) -> dict:
    return {
        "verb": a.verb,
        "actor": a.actor,
        "target": a.target,
        "location": a.location,
        "event_type": a.event_type.value,
        "confidence": a.confidence,
    }


def _event_dict(e: Any) -> dict:
    return {
        "event_type": e.event_type.value,
        "subject": e.subject,
        "predicate": e.predicate,
        "target": e.target,
        "action": e.action,
        "location": e.location,
        "attributes": e.attributes,
        "timestamp": e.timestamp.isoformat(),
        "source_scene": e.source_scene,
        "is_flashback": e.is_flashback,
    }


def _build_typed_events(events: list[Any], event_ids: list[str]) -> list[TypedEvent]:
    typed: list[TypedEvent] = []
    for index, event in enumerate(events):
        event_type = str(event.event_type.value)
        event_id = event_ids[index] if index < len(event_ids) else f"evt-{index + 1}"
        subject_type = EntityType.CHARACTER if event_type in {
            "character_appears", "character_exits", "character_changes", "death", "murder", "injury", "birth", "resurrection", "marriage", "betrayal", "alliance", "conflict", "discovery", "travel", "capture", "escape", "relationship_forms", "relationship_changes"
        } else (EntityType.SCENE if event_type in {"scene_opens", "scene_closes"} else (EntityType.LOCATION if event_type == "world_state_change" else EntityType.CONCEPT))
        if event.target:
            target_type = EntityType.CHARACTER if event_type in {"murder", "injury", "marriage", "betrayal", "alliance", "conflict", "capture", "relationship_forms", "relationship_changes", "discovery"} else EntityType.CONCEPT
        else:
            target_type = None

        typed.append(TypedEvent(
            event_id=event_id,
            event_type=event_type,
            subject=event.subject,
            subject_type=subject_type,
            predicate=event.predicate,
            target=event.target,
            target_type=target_type,
            location=event.location,
            attributes=dict(event.attributes),
        ))
    return typed


def _build_ontology_projection(entities: Any, typed_events: list[TypedEvent]) -> tuple[EntityRegistry, list[dict[str, Any]], list[Any]]:
    registry = EntityRegistry()
    validation_errors: list[dict[str, Any]] = []
    relationships: list[Any] = []

    for item in entities.characters:
        registry.register(item.name, EntityType.CHARACTER, attributes=item.attributes)
    for item in entities.locations:
        registry.register(item.name, EntityType.LOCATION, attributes=item.attributes)
    for item in entities.objects:
        registry.register(item.name, EntityType.OBJECT, attributes=item.attributes)
    for item in entities.concepts:
        registry.register(item.name, EntityType.CONCEPT, attributes=item.attributes)

    for event in typed_events:
        registry.register(event.subject, event.subject_type, event_id=event.event_id)
        if event.target and event.target_type is not None:
            registry.register(event.target, event.target_type, event_id=event.event_id)
        if event.location:
            registry.register(event.location, EntityType.LOCATION, event_id=event.event_id)

        errors = validate_typed_event(event)
        if errors:
            validation_errors.append({
                "event_id": event.event_id,
                "event_type": event.event_type,
                "errors": errors,
            })

        edge = relationship_edge_for_event(event)
        if edge is not None:
            relationships.append(edge)

    return registry, validation_errors, relationships
