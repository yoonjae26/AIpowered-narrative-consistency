from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.main import app


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        rows.append(
            {
                "id": str(payload.get("id") or "sample"),
                "text": str(payload.get("text") or ""),
                "expected_issue_types": [str(item) for item in (payload.get("expected_issue_types") or [])],
            }
        )
    return rows


def _predict_issue_types(client: TestClient, text: str) -> set[str]:
    response = client.post(
        "/narrative/rewrite/structured",
        json={
            "source_text": text,
            "scene_title": "Verifier benchmark",
            "instructions": "Only detect issues and produce minimal patch candidates.",
            "preserve_canon": True,
            "preserve_characters": True,
            "max_issues": 12,
            "candidates_per_issue": 2,
            "auto_apply": False,
            "strict_reverification": True,
            "use_knowledge_graph_evidence": True,
            "style_notes": ["benchmark", "minimal edits"],
        },
    )
    response.raise_for_status()
    payload = response.json()
    issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    return {str(issue.get("type") or "") for issue in issues if str(issue.get("type") or "")}


def evaluate(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    client = TestClient(app)

    per_type = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    sample_results: list[dict[str, Any]] = []

    for sample in dataset:
        expected = set(sample["expected_issue_types"])
        predicted = _predict_issue_types(client, sample["text"])

        for issue_type in predicted.intersection(expected):
            per_type[issue_type]["tp"] += 1
        for issue_type in predicted.difference(expected):
            per_type[issue_type]["fp"] += 1
        for issue_type in expected.difference(predicted):
            per_type[issue_type]["fn"] += 1

        sample_results.append(
            {
                "id": sample["id"],
                "expected": sorted(expected),
                "predicted": sorted(predicted),
                "matched": sorted(predicted.intersection(expected)),
                "missed": sorted(expected.difference(predicted)),
                "extra": sorted(predicted.difference(expected)),
            }
        )

    type_metrics: dict[str, Any] = {}
    total_tp = total_fp = total_fn = 0
    for issue_type, counts in sorted(per_type.items()):
        tp = counts["tp"]
        fp = counts["fp"]
        fn = counts["fn"]
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        type_metrics[issue_type] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn

    micro_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    micro_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    micro_f1 = (2 * micro_precision * micro_recall / (micro_precision + micro_recall)) if (micro_precision + micro_recall) else 0.0

    macro_precision = sum(metric["precision"] for metric in type_metrics.values()) / max(1, len(type_metrics))
    macro_recall = sum(metric["recall"] for metric in type_metrics.values()) / max(1, len(type_metrics))
    macro_f1 = sum(metric["f1"] for metric in type_metrics.values()) / max(1, len(type_metrics))

    return {
        "dataset_size": len(dataset),
        "summary": {
            "micro_precision": round(micro_precision, 4),
            "micro_recall": round(micro_recall, 4),
            "micro_f1": round(micro_f1, 4),
            "macro_precision": round(macro_precision, 4),
            "macro_recall": round(macro_recall, 4),
            "macro_f1": round(macro_f1, 4),
            "total_tp": total_tp,
            "total_fp": total_fp,
            "total_fn": total_fn,
        },
        "per_type": type_metrics,
        "samples": sample_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifier precision/recall evaluation")
    parser.add_argument(
        "--dataset",
        type=str,
        default="datasets/benchmarks/verifier_benchmark_dataset.jsonl",
    )
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    dataset = _load_dataset(dataset_path)
    result = evaluate(dataset)
    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    print(output_text)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
