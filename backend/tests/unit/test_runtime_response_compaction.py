from __future__ import annotations

from backend.narrative.mutation.entity_extractor import EntityExtractor
from backend.narrative.reality.knowledge_graph import NarrativeKnowledgeGraph
from backend.narrative.response_formatter import format_mutation_api_response


def test_response_formatter_exposes_compact_payload_only() -> None:
    runtime_result = {
        "success": True,
        "scene_title": "Compact Demo",
        "entities": {
            "characters": [{"name": "John"}, {"name": "John"}, {"name": "Mira"}],
            "locations": [{"name": "castle"}],
            "objects": [],
            "concepts": [{"name": "betrayal"}],
        },
        "events": [
            {"event_type": "murder"},
            {"event_type": "alliance"},
            {"event_type": "alliance"},
        ],
        "mutation": {
            "scene_id": "scene-1",
            "events_applied_count": 3,
            "characters_upserted": ["a", "b"],
            "upserted_entities": [{"id": "a", "name": "John"}, {"id": "b", "name": "Mira"}],
            "character_upsert_attempts": 3,
            "timeline_events_created": ["t1"],
        },
        "consistency": {"consistent": True, "warnings": ["w1"], "errors": []},
        "timeline": {"valid": True, "conflicts": [], "flashback_count": 0, "flash_forward_count": 1},
        "knowledge_graph": {
            "summary": {"node_count": 7, "edge_count": 5},
            "scene_projection": {"node_count": 3, "edge_count": 2},
        },
        "semantic_validation": {"issues": [{"rule_id": "r1"}]},
        "drift": {"issues": []},
        "multi_agent_analysis": {
            "agents": {"lore": {"role": "canon", "findings": ["canon conflict"]}},
            "structured_summary": [
                {"agent": "character", "score": 0.91, "primary_trait": "guilt_conflict", "risk": "low", "severity": "minor"}
            ],
            "blocking_issues": ["canon conflict"],
        },
        "analysis_enrichment": {"status": "cached", "cache_hit": True, "scene_hash": "hash-1"},
        "writer_warnings": [
            {"rule_id": "dialogue_inconsistency", "severity": "warning", "message": "msg", "suggestion": "fix"}
        ],
        "reasoning": {"evidence_chains": ["giant"]},
        "memory": {"retrieved": {"scenes": ["noisy"]}},
        "ontology": {"entity_registry": {}},
        "event_sourcing": {"ordering_applied": ["evt-1", "evt-2"]},
    }

    payload = format_mutation_api_response(runtime_result)

    assert payload["success"] is True
    assert payload["entities"]["characters"] == ["John", "Mira"]
    assert payload["events"]["types"]["alliance"] == 2
    assert payload["mutation"]["characters_upserted_count"] == 2
    assert payload["mutation"]["duplicate_upsert_attempts"] == 1
    assert payload["mutation"]["upserted_entities"] == [{"id": "a", "name": "John"}, {"id": "b", "name": "Mira"}]
    assert payload["analysis"]["agent_summary"] == [
        {"agent": "character", "score": 0.91, "primary_trait": "guilt_conflict", "risk": "low", "severity": "minor"}
    ]
    assert payload["analysis"]["enrichment_status"] == "cached"
    assert payload["analysis"]["cache_hit"] is True
    assert payload["analysis"]["scene_hash"] == "hash-1"
    assert payload["quality"]["critical_issues"] == 0
    assert payload["quality"]["major_issues"] == 1
    assert payload["quality"]["minor_issues"] == 0
    assert payload["knowledge_graph"]["node_count"] == 3
    assert payload["knowledge_graph"]["total_node_count"] == 7
    assert payload["meta"]["response_version"] == "v2_compact"

    assert "reasoning" not in payload
    assert "memory" not in payload
    assert "ontology" not in payload
    assert "event_sourcing" not in payload


def test_entity_extractor_normalizes_temporal_prefix_names() -> None:
    extractor = EntityExtractor(llm_provider=None, character_repo=None)

    entities = extractor.extract("After John entered the castle. Later John met Mira.")
    names = [item.name for item in entities.characters]

    assert "After" not in names
    assert "Later John" not in names
    assert "John" in names


def test_knowledge_graph_deduplicates_edges_and_increments_weight(tmp_path) -> None:
    graph = NarrativeKnowledgeGraph(file_path=tmp_path / "kg.json")

    graph.integrate_scene(
        typed_events=[
            {
                "event_id": "evt-1",
                "event_type": "alliance",
                "subject": "John",
                "subject_type": "character",
                "target": "Mira",
                "target_type": "character",
                "predicate": "John forms alliance with Mira",
                "happened_at": "t1",
            }
        ],
        scene_title="S1",
    )
    graph.integrate_scene(
        typed_events=[
            {
                "event_id": "evt-2",
                "event_type": "alliance",
                "subject": "John",
                "subject_type": "character",
                "target": "Mira",
                "target_type": "character",
                "predicate": "John reinforces alliance with Mira",
                "happened_at": "t2",
            }
        ],
        scene_title="S2",
    )

    summary = graph.summary()

    assert summary["edge_count"] == 1
    edges = list(graph._edges.values())
    assert edges[0].attributes["weight"] == 2


def test_mutation_result_uses_unique_upsert_count_in_response() -> None:
    runtime_result = {
        "success": True,
        "scene_title": "Mutation Count Demo",
        "entities": {"characters": [], "locations": [], "objects": [], "concepts": []},
        "events": [],
        "mutation": {
            "scene_id": "scene-x",
            "events_applied_count": 0,
            "characters_upserted": ["john", "john", "mira"],
            "upserted_entities": [
                {"id": "john", "name": "John"},
                {"id": "mira", "name": "Mira"},
            ],
            "character_upsert_attempts": 3,
            "timeline_events_created": [],
        },
        "consistency": {"consistent": True, "warnings": [], "errors": []},
        "timeline": {"valid": True, "conflicts": [], "flashback_count": 0, "flash_forward_count": 0},
        "knowledge_graph": {"summary": {"node_count": 0, "edge_count": 0}, "scene_projection": {"node_count": 0, "edge_count": 0}},
        "semantic_validation": {"issues": []},
        "drift": {"issues": []},
        "multi_agent_analysis": {"agents": {}, "structured_summary": []},
        "writer_warnings": [],
    }

    payload = format_mutation_api_response(runtime_result)

    assert payload["mutation"]["characters_upserted_count"] == 2
    assert payload["mutation"]["duplicate_upsert_attempts"] == 1
