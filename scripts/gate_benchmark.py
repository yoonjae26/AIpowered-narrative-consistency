from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from backend.consistency.checkers.semantic_validator import SemanticIssue, SemanticValidationResult
from backend.narrative.reality import ExplainableReasoningEngine
from backend.narrative.state_engine import NarrativeStateMutationEngine


@dataclass(slots=True)
class GateCase:
    name: str
    expected: str
    allow_canon_override: bool
    canon_conflict_severity: str | None = None
    consistency_errors: list[str] | None = None
    drift_errors: list[str] | None = None
    semantic_errors: list[str] | None = None
    chronology_conflicts: list[str] | None = None


@dataclass(slots=True)
class GateRun:
    expected: str
    actual: str
    correct: bool


class _ChronologyReport(SimpleNamespace):
    valid: bool = True
    conflicts: list[str]


def _engine() -> NarrativeStateMutationEngine:
    return object.__new__(NarrativeStateMutationEngine)


def _make_issue(message: str, severity: str = "error", rule_id: str = "benchmark", category: str = "benchmark") -> SemanticIssue:
    return SemanticIssue(
        rule_id=rule_id,
        category=category,
        severity=severity,
        message=message,
        evidence=[message],
        entities=["benchmark"],
        source="benchmark",
    )


def _build_case(case: GateCase) -> tuple[dict[str, Any], str]:
    consistency_report = SimpleNamespace(
        consistent=not bool(case.consistency_errors),
        warnings=[],
        errors=list(case.consistency_errors or []),
    )
    drift_issues = [
        SimpleNamespace(
            rule_id="drift_benchmark",
            severity="error",
            message=message,
            evidence=[message],
            character="benchmark",
        )
        for message in (case.drift_errors or [])
    ]
    semantic_result = SemanticValidationResult(
        score=0.42 if case.semantic_errors else 0.98,
        issues=[_make_issue(message) for message in (case.semantic_errors or [])],
        notes=["benchmark"],
        provider_used=None,
    )
    canon_conflicts = []
    if case.canon_conflict_severity is not None:
        canon_conflicts.append(
            SimpleNamespace(
                rule_id="canon_benchmark",
                severity=case.canon_conflict_severity,
                message="canon conflict",
                entities=["benchmark"],
            )
        )
    chronology_report = _ChronologyReport(conflicts=list(case.chronology_conflicts or []))

    gate = _engine()._resolve_gate_decision(
        allow_canon_override=case.allow_canon_override,
        verified_character_names=["Benchmark Character"],
        skipped_character_names=[],
        verification_events=[object()],
        preflight_character_memories={"Benchmark Character": SimpleNamespace()},
        canon_conflicts=canon_conflicts,
        consistency_report=consistency_report,
        drift_issues=drift_issues,
        semantic_result=semantic_result,
        chronology_report=chronology_report,
    )
    audit_preview = ExplainableReasoningEngine().build(
        semantic_issues=semantic_result.issues,
        drift_issues=drift_issues,
        canon_conflicts=canon_conflicts,
        chronology_conflicts=list(case.chronology_conflicts or []),
        multi_agent_report=None,
    )
    return {
        "gate": gate,
        "reasoning": audit_preview,
    }, gate["decision"]


def _benchmark_cases() -> list[GateCase]:
    cases: list[GateCase] = [
        GateCase("approve_clean", "approve", True),
        GateCase("approve_clean_2", "approve", False),
        GateCase("approve_clean_3", "approve", True),
        GateCase("reject_consistency", "reject", True, consistency_errors=["consistency failure"]),
        GateCase("reject_drift", "reject", True, drift_errors=["drift failure"]),
        GateCase("reject_semantic", "reject", True, semantic_errors=["semantic failure"]),
        GateCase("reject_timeline", "reject", True, chronology_conflicts=["timeline conflict"]),
        GateCase("override_canon", "needs-override", False, canon_conflict_severity="error"),
        GateCase("approve_canon_override", "approve", True, canon_conflict_severity="error"),
        GateCase("approve_warning_only", "approve", False, canon_conflict_severity="warning"),
        GateCase("reject_multi_signal", "reject", False, canon_conflict_severity="error", semantic_errors=["semantic failure"]),
        GateCase("reject_multi_signal_2", "reject", True, canon_conflict_severity="warning", chronology_conflicts=["timeline conflict"], drift_errors=["drift failure"]),
    ]
    return cases


def run_benchmark() -> dict[str, Any]:
    cases = _benchmark_cases()
    results: list[GateRun] = []
    details: list[dict[str, Any]] = []
    counts = Counter()

    for case in cases:
        payload, actual = _build_case(case)
        run = GateRun(expected=case.expected, actual=actual, correct=actual == case.expected)
        results.append(run)
        counts[case.expected] += 1
        details.append(
            {
                "name": case.name,
                "expected": case.expected,
                "actual": actual,
                "correct": run.correct,
                "trace_count": payload["reasoning"]["trace_count"],
                "evidence_chain_count": len(payload["reasoning"]["evidence_chains"]),
            }
        )

    accuracy = sum(1 for item in results if item.correct) / len(results) if results else 0.0
    confusion = defaultdict(lambda: Counter())
    for item in results:
        confusion[item.expected][item.actual] += 1

    return {
        "cases": len(cases),
        "accuracy": round(accuracy, 4),
        "label_counts": dict(counts),
        "confusion_matrix": {expected: dict(actuals) for expected, actuals in confusion.items()},
        "details": details,
    }


def _random_case(rng: random.Random, idx: int) -> GateCase:
    roll = rng.random()
    if roll < 0.55:
        return GateCase(f"scene_{idx}_approve", "approve", rng.choice([True, False]))
    if roll < 0.75:
        return GateCase(f"scene_{idx}_override", "needs-override", False, canon_conflict_severity="error")
    if roll < 0.88:
        return GateCase(f"scene_{idx}_reject_consistency", "reject", True, consistency_errors=["consistency failure"])
    if roll < 0.94:
        return GateCase(f"scene_{idx}_reject_semantic", "reject", True, semantic_errors=["semantic failure"])
    return GateCase(f"scene_{idx}_reject_timeline", "reject", True, chronology_conflicts=["timeline conflict"])


def run_stress(sizes: list[int], seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    runs: list[dict[str, Any]] = []
    for size in sizes:
        cases = [_random_case(rng, index) for index in range(size)]
        start = time.perf_counter()
        outcomes = Counter()
        for case in cases:
            _, decision = _build_case(case)
            outcomes[decision] += 1
        elapsed = time.perf_counter() - start
        runs.append(
            {
                "scenes": size,
                "elapsed_seconds": round(elapsed, 4),
                "throughput_scenes_per_second": round(size / elapsed, 2) if elapsed > 0 else None,
                "decision_counts": dict(outcomes),
            }
        )
    return {"seed": seed, "runs": runs}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the narrative gate and reasoning surfaces.")
    parser.add_argument("--stress", nargs="*", type=int, default=[100, 500, 1000], help="Scene counts to stress test.")
    parser.add_argument("--skip-stress", action="store_true", help="Only run the benchmark suite.")
    args = parser.parse_args()

    benchmark = run_benchmark()
    output = {"benchmark": benchmark}

    if not args.skip_stress:
        output["stress"] = run_stress(args.stress)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
