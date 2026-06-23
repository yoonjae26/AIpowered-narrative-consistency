from __future__ import annotations

import json
from pathlib import Path

from backend.observability.metrics import compute_consistency_metrics


def _load_dataset(file_name: str) -> dict[str, object]:
    path = Path("datasets") / file_name
    return json.loads(path.read_text(encoding="utf-8"))


def test_benchmark_datasets_have_expected_schema() -> None:
    datasets = [
        _load_dataset("dead_character_reappears.json"),
        _load_dataset("canon_conflict.json"),
        _load_dataset("timeline_break.json"),
        _load_dataset("contradiction_benchmark.json"),
        _load_dataset("long_horizon_corruption.json"),
        _load_dataset("personality_drift.json"),
        _load_dataset("retrieval_corruption.json"),
        _load_dataset("branch_conflict.json"),
    ]

    for item in datasets:
        assert isinstance(item.get("dataset"), str)
        assert isinstance(item.get("version"), str)
        cases = item.get("cases")
        assert isinstance(cases, list) and cases
        for case in cases:
            assert isinstance(case.get("id"), str)
            assert isinstance(case.get("scene_title"), str)
            assert isinstance(case.get("scene_text"), str)
            expected = case.get("expected")
            assert isinstance(expected, dict)
            assert isinstance(expected.get("should_flag"), bool)
            assert isinstance(expected.get("rule_ids"), list)
            assert expected.get("severity") in {"error", "warning", "info"}


def test_consistency_metrics_values_are_bounded_and_interpretable() -> None:
    payload = {
        "timeline": {
            "conflicts": ["resurrection before death"],
            "flashback_count": 2,
        },
        "consistency": {
            "errors": ["dead character reappears"],
            "warnings": ["dialogue inconsistency"],
        },
        "drift": {
            "issues": [
                {"rule_id": "personality_collapse", "severity": "error"},
            ],
        },
        "canon_protection": {
            "conflicts": [
                {"rule_id": "canon_immutable_override", "severity": "error"},
                {"rule_id": "lore_conflict_detected", "severity": "warning"},
            ],
        },
        "semantic_validation": {
            "issues": [
                {"rule_id": "dialogue_inconsistency", "severity": "warning"},
                {"rule_id": "unnatural_progression", "severity": "warning"},
            ],
        },
    }

    metrics = compute_consistency_metrics(payload)
    summary = metrics.as_dict()

    assert 0.0 <= summary["timeline_accuracy"] <= 1.0
    assert 0.0 <= summary["character_consistency"] <= 1.0
    assert 0.0 <= summary["canon_integrity"] <= 1.0
    assert 0.0 <= summary["overall_consistency"] <= 1.0
    assert summary["overall_consistency"] <= 0.8
