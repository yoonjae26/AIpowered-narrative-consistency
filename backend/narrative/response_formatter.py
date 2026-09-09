from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping


RuntimeMutationResult = Mapping[str, Any]


@dataclass(slots=True)
class MutationAPIResponse:
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return self.payload


def format_mutation_api_response(runtime_result: RuntimeMutationResult) -> dict[str, Any]:
    success = bool(runtime_result.get("success", False))
    scene_title = runtime_result.get("scene_title")
    gate = runtime_result.get("gate") or {}
    decision = str(runtime_result.get("decision") or gate.get("decision") or ("approve" if success else "reject"))

    if not success:
        raw_pbkd = runtime_result.get("pbkd_reasoning") or {}
        raw_kg_conflicts = runtime_result.get("kg_conflicts") or []
        return MutationAPIResponse(
            payload={
                "success": False,
                "scene_title": scene_title,
                "error": runtime_result.get("error", "Unknown pipeline error"),
                "decision": decision,
                "gate": _compact_gate(gate, fallback_decision=decision),
                "preflight": _compact_preflight(runtime_result.get("preflight") or {}),
                "audit": _compact_audit(runtime_result.get("audit_trail") or {}),
                "pbkd_reasoning": {
                    "inferences": [
                        {
                            "character": str(inf.get("character") or ""),
                            "action": str(inf.get("action") or ""),
                            "verdict": str(inf.get("verdict") or "ambiguous"),
                            "dimension": str(inf.get("dimension") or "B"),
                            "chain": str(inf.get("chain") or ""),
                            "severity": str(inf.get("severity") or "minor"),
                        }
                        for inf in (raw_pbkd.get("inferences") or [])
                        if isinstance(inf, Mapping)
                    ],
                    "contradiction_count": int(raw_pbkd.get("contradiction_count") or 0),
                },
                "kg_conflicts": [
                    {
                        "character_a": str(c.get("character_a") or ""),
                        "character_b": str(c.get("character_b") or ""),
                        "stored_relation": str(c.get("stored_relation") or ""),
                        "new_event": str(c.get("new_event") or ""),
                        "weight": int(c.get("weight") or 1),
                        "severity": str(c.get("severity") or "minor"),
                        "chain": str(c.get("chain") or ""),
                    }
                    for c in raw_kg_conflicts
                    if isinstance(c, Mapping)
                ],
                "meta": {"response_version": "v2_compact"},
            }
        ).as_dict()

    entities = runtime_result.get("entities") or {}
    events = runtime_result.get("events") or []
    mutation = runtime_result.get("mutation") or {}
    consistency = runtime_result.get("consistency") or {}
    timeline = runtime_result.get("timeline") or {}
    semantic_validation = runtime_result.get("semantic_validation") or {}
    drift = runtime_result.get("drift") or {}
    multi_agent = runtime_result.get("multi_agent_analysis") or {}
    raw_kg_conflicts_success = runtime_result.get("kg_conflicts") or []
    analysis_enrichment = runtime_result.get("analysis_enrichment") or {}
    audit_trail = runtime_result.get("audit_trail") or {}
    writer_warnings = runtime_result.get("writer_warnings") or []
    knowledge_graph = runtime_result.get("knowledge_graph") or {}
    pbkd_reasoning = runtime_result.get("pbkd_reasoning") or {}
    graph_summary = (knowledge_graph.get("summary")) or {}
    scene_graph = (knowledge_graph.get("scene_projection")) or graph_summary
    quality_breakdown = _quality_breakdown(writer_warnings, consistency, multi_agent)
    upserted_entities = _compact_upserted_entities(mutation.get("upserted_entities") or [])

    event_type_counts = Counter(
        str(item.get("event_type"))
        for item in events
        if isinstance(item, dict) and item.get("event_type")
    )

    response = MutationAPIResponse(
        payload={
            "success": True,
            "scene_title": scene_title,
            "entities": {
                "characters": _dedupe_names(entities.get("characters") or []),
                "locations": _dedupe_names(entities.get("locations") or []),
                "objects": _dedupe_names(entities.get("objects") or []),
                "concepts": _dedupe_names(entities.get("concepts") or []),
            },
            "events": {
                "count": len(events),
                "types": dict(event_type_counts),
            },
            "mutation": {
                "scene_id": mutation.get("scene_id"),
                "events_applied_count": int(mutation.get("events_applied_count") or 0),
                "characters_upserted_count": len(upserted_entities),
                "character_upsert_attempts": int(mutation.get("character_upsert_attempts") or len(upserted_entities)),
                "duplicate_upsert_attempts": max(0, int(mutation.get("character_upsert_attempts") or len(upserted_entities)) - len(upserted_entities)),
                "upserted_entities": upserted_entities,
                "timeline_events_created_count": len(mutation.get("timeline_events_created") or []),
            },
            "quality": {
                "consistent": bool(consistency.get("consistent", True)),
                "warning_count": len(consistency.get("warnings") or []),
                "error_count": len(consistency.get("errors") or []),
                "semantic_issue_count": len(semantic_validation.get("issues") or []),
                "drift_issue_count": len(drift.get("issues") or []),
                "critical_issues": quality_breakdown["critical_issues"],
                "major_issues": quality_breakdown["major_issues"],
                "minor_issues": quality_breakdown["minor_issues"],
            },
            "timeline": {
                "valid": bool(timeline.get("valid", True)),
                "conflicts_count": len(timeline.get("conflicts") or []),
                "flashback_count": int(timeline.get("flashback_count") or 0),
                "flash_forward_count": int(timeline.get("flash_forward_count") or 0),
            },
            "knowledge_graph": {
                "node_count": int(scene_graph.get("node_count") or 0),
                "edge_count": int(scene_graph.get("edge_count") or 0),
                "total_node_count": int(graph_summary.get("node_count") or 0),
                "total_edge_count": int(graph_summary.get("edge_count") or 0),
            },
            "analysis": {
                "agent_summary": _structured_agent_summary(multi_agent),
                "enrichment_status": str(analysis_enrichment.get("status") or "fast_path"),
                "cache_hit": bool(analysis_enrichment.get("cache_hit", False)),
                "scene_hash": str(analysis_enrichment.get("scene_hash") or ""),
                "top_warnings": _compact_writer_warnings(writer_warnings),
            },
            "audit": _compact_audit(audit_trail),
            "gate": _compact_gate(gate, fallback_decision=decision),
            "pbkd_reasoning": {
                "inferences": [
                    {
                        "character": str(inf.get("character") or ""),
                        "action": str(inf.get("action") or ""),
                        "verdict": str(inf.get("verdict") or "ambiguous"),
                        "dimension": str(inf.get("dimension") or "B"),
                        "chain": str(inf.get("chain") or ""),
                        "severity": str(inf.get("severity") or "minor"),
                    }
                    for inf in (pbkd_reasoning.get("inferences") or [])
                    if isinstance(inf, Mapping)
                ],
                "contradiction_count": int(pbkd_reasoning.get("contradiction_count") or 0),
            },
            "kg_conflicts": [
                {
                    "character_a": str(c.get("character_a") or ""),
                    "character_b": str(c.get("character_b") or ""),
                    "stored_relation": str(c.get("stored_relation") or ""),
                    "new_event": str(c.get("new_event") or ""),
                    "weight": int(c.get("weight") or 1),
                    "severity": str(c.get("severity") or "minor"),
                    "chain": str(c.get("chain") or ""),
                }
                for c in raw_kg_conflicts_success
                if isinstance(c, Mapping)
            ],
            "meta": {"response_version": "v2_compact"},
        }
    )
    return response.as_dict()


def _dedupe_names(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        raw_name = str(item.get("canonical_name") or item.get("name") or "").strip()
        if not raw_name:
            continue
        key = raw_name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(raw_name)
    return names


def _structured_agent_summary(multi_agent: Mapping[str, Any]) -> list[dict[str, Any]]:
    structured = multi_agent.get("structured_summary") or []
    compact: list[dict[str, Any]] = []
    for item in structured:
        if not isinstance(item, Mapping):
            continue
        compact.append(
            {
                "agent": str(item.get("agent") or ""),
                "score": float(item.get("score") or 0.0),
                "primary_trait": str(item.get("primary_trait") or "general_consistency"),
                "risk": str(item.get("risk") or "low"),
                "severity": str(item.get("severity") or "minor"),
            }
        )
    return compact


def _compact_writer_warnings(warnings: list[Any], limit: int = 8) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    for item in warnings[:limit]:
        if not isinstance(item, Mapping):
            continue
        compact.append(
            {
                "rule_id": str(item.get("rule_id") or ""),
                "severity": str(item.get("severity") or ""),
                "message": _truncate_text(str(item.get("message") or ""), 220),
                "suggestion": _truncate_text(str(item.get("suggestion") or ""), 180),
            }
        )
    return compact


def _compact_gate(gate: Mapping[str, Any], fallback_decision: str = "approve") -> dict[str, Any]:
    if not isinstance(gate, Mapping):
        gate = {}
    return {
        "decision": str(gate.get("decision") or fallback_decision),
        "approved": bool(gate.get("approved", str(gate.get("decision") or fallback_decision) == "approve")),
        "allow_canon_override": bool(gate.get("allow_canon_override", False)),
        "blocking_reason_count": len(gate.get("blocking_reasons") or []),
        "overrideable_reason_count": len(gate.get("overrideable_reasons") or []),
        "non_overrideable_reason_count": len(gate.get("non_overrideable_reasons") or []),
        "message": str(gate.get("message") or ""),
        "summary": gate.get("summary") or {},
        "blocking_reasons": list(gate.get("blocking_reasons") or [])[:8],
        "overrideable_reasons": list(gate.get("overrideable_reasons") or [])[:8],
        "non_overrideable_reasons": list(gate.get("non_overrideable_reasons") or [])[:8],
    }


def _compact_preflight(preflight: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(preflight, Mapping):
        preflight = {}
    timeline = preflight.get("timeline") or {}
    consistency = preflight.get("consistency") or {}
    semantic_validation = preflight.get("semantic_validation") or {}
    drift = preflight.get("drift") or {}
    canon = preflight.get("canon_protection") or {}
    ontology = preflight.get("ontology") or {}
    return {
        "verification_scope": preflight.get("verification_scope") or {},
        "timeline": {
            "valid": bool(timeline.get("valid", True)),
            "conflicts_count": len(timeline.get("conflicts") or []),
            "flashback_count": int(timeline.get("flashback_count") or 0),
            "flash_forward_count": int(timeline.get("flash_forward_count") or 0),
        },
        "consistency": {
            "consistent": bool(consistency.get("consistent", True)),
            "warning_count": len(consistency.get("warnings") or []),
            "error_count": len(consistency.get("errors") or []),
        },
        "semantic_issue_count": len(semantic_validation.get("issues") or []),
        "drift_issue_count": len(drift.get("issues") or []),
        "canon_conflict_count": len(canon.get("conflicts") or []),
        "ontology_error_count": len(ontology.get("validation_errors") or []),
    }


def _quality_breakdown(
    warnings: list[Any],
    consistency: Mapping[str, Any],
    multi_agent: Mapping[str, Any],
) -> dict[str, int]:
    counts = {
        "critical_issues": 0,
        "major_issues": 0,
        "minor_issues": 0,
    }

    for item in warnings:
        if not isinstance(item, Mapping):
            continue
        severity = str(item.get("severity") or "warning").lower()
        rule_id = str(item.get("rule_id") or "")
        if severity == "error":
            counts["critical_issues"] += 1
        elif rule_id in {"timeline_conflict", "personality_collapse", "dialogue_inconsistency", "unnatural_progression"}:
            counts["major_issues"] += 1
        else:
            counts["minor_issues"] += 1

    if not warnings:
        structured = multi_agent.get("structured_summary") or []
        for item in structured:
            if not isinstance(item, Mapping):
                continue
            severity = str(item.get("severity") or "none")
            if severity == "critical":
                counts["critical_issues"] += 1
            elif severity == "major":
                counts["major_issues"] += 1
            elif severity == "minor":
                counts["minor_issues"] += 1

    counts["critical_issues"] += len(consistency.get("errors") or [])
    return counts


def _compact_upserted_entities(items: list[Any]) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        entity_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        compact.append({"id": entity_id, "name": name})
    return compact


def _compact_audit(audit_trail: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(audit_trail, Mapping):
        audit_trail = {}
    reasoning = audit_trail.get("reasoning") or {}
    verification = audit_trail.get("verification") or {}
    replay_verification = audit_trail.get("replay_verification") or {}
    gate = audit_trail.get("gate") or {}
    evidence_chains = list(reasoning.get("evidence_chains") or [])
    return {
        "scene_id": audit_trail.get("scene_id"),
        "scene_title": audit_trail.get("scene_title"),
        "branch": str(audit_trail.get("branch") or "main"),
        "decision": str(audit_trail.get("decision") or "reject"),
        "rejected_before_persist": bool(audit_trail.get("rejected_before_persist", False)),
        "scene_hash": str(audit_trail.get("scene_hash") or ""),
        "evidence_chain_count": len(evidence_chains),
        "trace_count": int(reasoning.get("trace_count") or 0),
        "blocking_reason_count": len(gate.get("blocking_reasons") or []),
        "timeline_conflict_count": len((verification.get("timeline") or {}).get("conflicts") or []),
        "canon_conflict_count": len((verification.get("canon_protection") or {}).get("conflicts") or []),
        "replay_verified": bool(replay_verification.get("valid", False)),
        "replay_checksum": str(replay_verification.get("replay_checksum") or ""),
    }


def _truncate_text(text: str, max_len: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."