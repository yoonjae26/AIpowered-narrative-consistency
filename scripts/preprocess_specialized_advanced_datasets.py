from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


KOCOSA_MODULES = [
    "subtext_reasoning",
    "emotional_contradiction",
    "dialogue_nuance",
    "advanced_semantic_validator",
]


@dataclass(slots=True)
class Stats:
    total_records: int = 0
    kocosa_records: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize Korean Sarcasm Dataset (KoCoSa) for NarrativeOS specialized advanced modules"
    )
    parser.add_argument(
        "--kocosa-dir",
        default="/home/hong/.cache/huggingface/hub/datasets--YuminKim--KoCoSa/snapshots/d6d570a423ea083e79c16f42bddb25bd6493c2b6",
        help="Path to KoCoSa snapshot root",
    )
    parser.add_argument(
        "--output-dir",
        default="datasets/normalized_specialized_advanced",
        help="Output directory for normalized records",
    )
    return parser.parse_args()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def detect_language(text: str) -> str:
    return "ko" if re.search(r"[\uac00-\ud7a3]", text or "") else "unknown"


def write_record(
    record: dict[str, Any],
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
) -> None:
    unified_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    for module in record.get("module_targets", []):
        if module in module_handles:
            module_handles[module].write(json.dumps(record, ensure_ascii=False) + "\n")
            module_counts[module] += 1


def split_name_from_file_name(name: str) -> str:
    lower = name.lower()
    if lower.startswith("train-"):
        return "train"
    if lower.startswith("validation-") or lower.startswith("dev-"):
        return "validation"
    if lower.startswith("test-"):
        return "test"
    return "train"


def build_kocosa_record(row: dict[str, Any], split_name: str, row_id: int) -> dict[str, Any] | None:
    context = normalize_whitespace(str(row.get("context") or ""))
    response = normalize_whitespace(str(row.get("response") or ""))
    label = normalize_whitespace(str(row.get("label") or ""))
    explanation = normalize_whitespace(str(row.get("sarcasm_explanation") or ""))

    if not context or not response:
        return None

    text_parts = [
        f"[context] {context}",
        f"[response] {response}",
        f"[sarcasm_label] {label or 'unknown'}",
    ]
    if explanation:
        text_parts.append(f"[subtext_explanation] {explanation}")
    text = "\n".join(text_parts)

    is_sarcasm = int(label.lower() == "sarcasm")

    return {
        "record_id": f"kocosa:{split_name}:{row_id}",
        "source_dataset": "Korean Sarcasm Dataset (KoCoSa)",
        "language": detect_language(text),
        "module_targets": list(KOCOSA_MODULES),
        "record_type": "conversation",
        "text": text,
        "source": {
            "split": split_name,
            "row_id": row_id,
        },
        "annotations": {
            "label": label or None,
            "sarcasm_explanation": explanation or None,
            "is_sarcasm": is_sarcasm,
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "context_length": len(context),
            "response_length": len(response),
            "is_sarcasm": is_sarcasm,
            "has_explanation": int(bool(explanation)),
        },
    }


def process_kocosa(
    kocosa_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    data_dir = kocosa_dir / "data"
    if not data_dir.exists():
        return

    for parquet_path in sorted(data_dir.glob("*.parquet")):
        split_name = split_name_from_file_name(parquet_path.name)
        parquet = pq.ParquetFile(parquet_path)
        row_id = 0
        for batch in parquet.iter_batches(batch_size=1024, columns=["context", "response", "label", "sarcasm_explanation"]):
            for row in batch.to_pylist():
                try:
                    record = build_kocosa_record(row=row, split_name=split_name, row_id=row_id)
                except Exception:
                    stats.parse_errors += 1
                    row_id += 1
                    continue
                row_id += 1
                if record is None:
                    continue
                write_record(record, unified_handle, module_handles, module_counts)
                stats.total_records += 1
                stats.kocosa_records += 1


def write_outputs(output_dir: Path, module_names: list[str]):
    output_dir.mkdir(parents=True, exist_ok=True)
    by_module_dir = output_dir / "by_module"
    manifests_dir = output_dir / "manifests"
    by_module_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    unified_handle = (output_dir / "unified.jsonl").open("w", encoding="utf-8")
    module_handles = {
        module: (by_module_dir / f"{module}.jsonl").open("w", encoding="utf-8")
        for module in sorted(set(module_names))
    }
    return unified_handle, module_handles, manifests_dir


def write_manifest(
    manifests_dir: Path,
    stats: Stats,
    module_counts: Counter[str],
    args: argparse.Namespace,
) -> None:
    payload = {
        "dataset": "NarrativeOS Specialized Advanced Normalized",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            "kocosa_dir": str(Path(args.kocosa_dir)),
        },
        "records": {
            "total": stats.total_records,
            "kocosa": stats.kocosa_records,
            "parse_errors": stats.parse_errors,
        },
        "module_record_counts": dict(module_counts),
        "notes": {
            "role": "advanced_semantic_validator_support",
            "not_primary_narrative_dataset": True,
        },
        "schema": {
            "record_id": "str",
            "source_dataset": "str",
            "language": "str",
            "module_targets": "list[str]",
            "record_type": "str",
            "text": "str",
            "source": "dict[str, Any]",
            "annotations": "dict[str, Any]",
            "features": "dict[str, Any]",
        },
    }
    (manifests_dir / "normalization_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_readme(output_dir: Path) -> None:
    text = """# NarrativeOS Specialized Advanced Normalized Datasets

This corpus contains:
- Korean Sarcasm Dataset (KoCoSa)

This corpus is intended for advanced semantic validator use-cases:
- subtext reasoning
- emotional contradiction
- dialogue nuance

Output:
- unified.jsonl
- by_module/*.jsonl
- manifests/normalization_manifest.json
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    stats = Stats()
    module_counts: Counter[str] = Counter()

    unified_handle, module_handles, manifests_dir = write_outputs(output_dir, KOCOSA_MODULES)
    try:
        process_kocosa(
            kocosa_dir=Path(args.kocosa_dir),
            unified_handle=unified_handle,
            module_handles=module_handles,
            module_counts=module_counts,
            stats=stats,
        )
    finally:
        unified_handle.close()
        for handle in module_handles.values():
            handle.close()

    write_manifest(manifests_dir, stats, module_counts, args)
    write_readme(output_dir)

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(output_dir),
                "records_total": stats.total_records,
                "kocosa_records": stats.kocosa_records,
                "parse_errors": stats.parse_errors,
                "module_record_counts": dict(module_counts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
