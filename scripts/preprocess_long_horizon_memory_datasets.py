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


WEBTEXT_MODULES = [
    "embeddings",
    "retrieval_memory",
    "semantic_indexing",
    "background_language_understanding",
]

MAX_TEXT_CHARS = 1400


@dataclass(slots=True)
class Stats:
    total_records: int = 0
    webtext_records: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize Korean WebText / OSCAR Korean for NarrativeOS long-horizon memory infrastructure"
    )
    parser.add_argument(
        "--webtext-dir",
        default="/home/hong/.cache/huggingface/hub/datasets--HAERAE-HUB--KOREAN-WEBTEXT/snapshots/2ad96e4983923d91350ab2214e059bd57219eddd",
        help="Path to Korean WebText snapshot root",
    )
    parser.add_argument(
        "--output-dir",
        default="datasets/normalized_long_horizon_memory",
        help="Output directory for normalized records",
    )
    return parser.parse_args()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def detect_language(text: str) -> str:
    return "ko" if re.search(r"[\uac00-\ud7a3]", text or "") else "unknown"


def compact_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    cleaned = text.replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    paragraphs = [normalize_whitespace(part) for part in re.split(r"\n+", cleaned) if normalize_whitespace(part)]

    selected: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if current_len >= max_chars:
            break
        remaining = max_chars - current_len
        piece = paragraph[:remaining].strip()
        if not piece:
            continue
        projected = current_len + len(piece) + (2 if selected else 0)
        if projected > max_chars and selected:
            break
        selected.append(piece)
        current_len = projected

    return "\n\n".join(selected)[:max_chars].strip()


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


def build_webtext_record(row: dict[str, Any], split_name: str) -> dict[str, Any] | None:
    raw_text = str(row.get("text") or "")
    compact = compact_text(raw_text)
    if not compact:
        return None

    source_name = normalize_whitespace(str(row.get("source") or "unknown"))
    token_count_raw = row.get("token_count")
    try:
        token_count = int(token_count_raw) if token_count_raw is not None else None
    except (TypeError, ValueError):
        token_count = None

    raw_index = row.get("__index_level_0__")
    record_id = f"korean_webtext:{raw_index if raw_index is not None else source_name}:{split_name}"
    text_body = "\n".join(
        [
            f"[source] {source_name}",
            f"[document] {compact}",
        ]
    )

    return {
        "record_id": record_id,
        "source_dataset": "KOREAN-WEBTEXT",
        "language": detect_language(text_body),
        "module_targets": list(WEBTEXT_MODULES),
        "record_type": "lore_entry",
        "text": text_body,
        "source": {
            "split": split_name,
            "source_name": source_name,
            "raw_index": raw_index,
        },
        "annotations": {
            "source_name": source_name,
            "token_count": token_count,
            "dataset_role": "semantic_infrastructure",
        },
        "features": {
            "char_length": len(text_body),
            "word_like_count": len(text_body.split()),
            "summary_chars": len(compact),
            "token_count": token_count,
        },
    }


def process_webtext(
    webtext_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    data_dir = webtext_dir / "data"
    if not data_dir.exists():
        return

    for parquet_path in sorted(data_dir.glob("*.parquet")):
        split_name = "train"
        parquet = pq.ParquetFile(parquet_path)
        for batch in parquet.iter_batches(batch_size=1024, columns=["text", "source", "token_count", "__index_level_0__"]):
            for row in batch.to_pylist():
                try:
                    record = build_webtext_record(row=row, split_name=split_name)
                except Exception:
                    stats.parse_errors += 1
                    continue
                if record is None:
                    continue
                write_record(record, unified_handle, module_handles, module_counts)
                stats.total_records += 1
                stats.webtext_records += 1


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
        "dataset": "NarrativeOS Long-Horizon Memory Normalized",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            "webtext_dir": str(Path(args.webtext_dir)),
        },
        "records": {
            "total": stats.total_records,
            "webtext": stats.webtext_records,
            "parse_errors": stats.parse_errors,
        },
        "module_record_counts": dict(module_counts),
        "notes": {
            "role": "semantic_infrastructure",
            "not_primary_narrative_dataset": True,
            "text_strategy": f"compact semantic document capped at {MAX_TEXT_CHARS} chars per record for retrieval efficiency",
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
    text = """# NarrativeOS Long-Horizon Memory Normalized Datasets

This infrastructure corpus contains:
- Korean WebText / OSCAR Korean

This corpus is intended for semantic infrastructure, embeddings, retrieval memory, semantic indexing, and background language understanding.

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

    unified_handle, module_handles, manifests_dir = write_outputs(output_dir, WEBTEXT_MODULES)
    try:
        process_webtext(
            webtext_dir=Path(args.webtext_dir),
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
                "webtext_records": stats.webtext_records,
                "parse_errors": stats.parse_errors,
                "module_record_counts": dict(module_counts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()