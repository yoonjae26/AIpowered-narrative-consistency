from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


WIKIPEDIA_MODULES = [
    "entity_linking",
    "ontology_building",
    "knowledge_graph",
    "semantic_retrieval",
]

NAMUWIKI_MODULES = [
    "lore_management",
    "canon_reasoning",
    "relationship_graph",
    "timeline_reasoning",
]

MAX_TEXT_CHARS = 1400


@dataclass(slots=True)
class Stats:
    total_records: int = 0
    wikipedia_records: int = 0
    namuwiki_records: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize Korean Wikipedia and NamuWiki for NarrativeOS ontology/knowledge-graph modules"
    )
    parser.add_argument(
        "--wikipedia-dir",
        default="/home/hong/.cache/huggingface/hub/datasets--eaglewatch--Korean_Wikipedia_Dataset_for_GPT2_August_2022/snapshots/46d2589714cbda34e9fd6368c43c350025467c40",
        help="Path to Korean Wikipedia dataset snapshot root",
    )
    parser.add_argument(
        "--namuwiki-dir",
        default="/home/hong/.cache/huggingface/hub/datasets--heegyu--namuwiki-extracted/snapshots/d5ef945611040f7f760e02abfdc05be74b01edbe",
        help="Path to namuwiki-extracted snapshot root",
    )
    parser.add_argument(
        "--output-dir",
        default="datasets/normalized_knowledge_graph_entity",
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


def compact_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    cleaned = text.replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"'''", "", cleaned)
    cleaned = re.sub(r"''", "", cleaned)
    paragraphs = [normalize_whitespace(part) for part in re.split(r"\n+", cleaned) if normalize_whitespace(part)]

    selected: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        piece = paragraph[: max_chars - current_len].strip()
        if not piece:
            continue
        projected = current_len + len(piece) + (2 if selected else 0)
        if projected > max_chars and selected:
            break
        selected.append(piece)
        current_len = projected
        if current_len >= max_chars:
            break

    return "\n\n".join(selected)[:max_chars].strip()


def extract_wikipedia_title(text: str) -> str:
    lead = text.lstrip()
    bold_match = re.match(r"'+([^'\n]{1,120})'+", lead)
    if bold_match:
        return normalize_whitespace(bold_match.group(1))

    sentence = re.split(r"[\.\n]", lead, maxsplit=1)[0]
    sentence = normalize_whitespace(sentence)
    if not sentence:
        return "Untitled Wikipedia Entry"
    return sentence[:80]


def stable_id(prefix: str, raw: str) -> str:
    return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def build_wikipedia_record(text: str, split_name: str) -> dict[str, Any] | None:
    normalized = compact_text(text)
    if not normalized:
        return None

    title = extract_wikipedia_title(text)
    text_body = "\n".join(
        [
            f"[title] {title}",
            f"[summary] {normalized}",
        ]
    )
    record_id = stable_id("kowiki", f"{split_name}:{title}:{normalized[:240]}")

    return {
        "record_id": record_id,
        "source_dataset": "Korean Wikipedia Dataset for GPT2 August 2022",
        "language": detect_language(text_body),
        "module_targets": list(WIKIPEDIA_MODULES),
        "record_type": "lore_entry",
        "text": text_body,
        "source": {
            "split": split_name,
            "title": title,
        },
        "annotations": {
            "title": title,
            "dataset_role": "ontology_foundation",
        },
        "features": {
            "char_length": len(text_body),
            "word_like_count": len(text_body.split()),
            "summary_chars": len(normalized),
        },
    }


def process_wikipedia(
    wikipedia_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    data_dir = wikipedia_dir / "data"
    if not data_dir.exists():
        return

    for parquet_path in sorted(data_dir.glob("*.parquet")):
        split_name = "validation" if parquet_path.name.startswith("valid-") else "train"
        parquet = pq.ParquetFile(parquet_path)
        for batch in parquet.iter_batches(batch_size=1024, columns=["text"]):
            for row in batch.to_pylist():
                try:
                    record = build_wikipedia_record(str(row.get("text") or ""), split_name=split_name)
                except Exception:
                    stats.parse_errors += 1
                    continue
                if record is None:
                    continue
                write_record(record, unified_handle, module_handles, module_counts)
                stats.total_records += 1
                stats.wikipedia_records += 1


def is_probable_timeline_text(text: str) -> bool:
    return bool(re.search(r"\b\d{3,4}년\b|연표|시기|시즌|화\b", text))


def build_namuwiki_record(row: dict[str, Any], row_id: int) -> dict[str, Any] | None:
    title = normalize_whitespace(str(row.get("title") or ""))
    raw_text = str(row.get("text") or "")
    namespace = normalize_whitespace(str(row.get("namespace") or ""))
    contributors = normalize_whitespace(str(row.get("contributors") or ""))
    normalized = compact_text(raw_text)
    if not title or not normalized:
        return None

    text_parts = [f"[title] {title}", f"[summary] {normalized}"]
    text_body = "\n".join(text_parts)
    task_hints = {
        "has_timeline_signal": is_probable_timeline_text(raw_text),
        "namespace": namespace,
    }

    return {
        "record_id": f"namuwiki:{row_id}",
        "source_dataset": "namuwiki-extracted",
        "language": detect_language(text_body),
        "module_targets": list(NAMUWIKI_MODULES),
        "record_type": "lore_entry",
        "text": text_body,
        "source": {
            "split": "train",
            "title": title,
            "namespace": namespace,
        },
        "annotations": {
            "title": title,
            "namespace": namespace or None,
            "contributor_count": len([item for item in contributors.split(",") if item.strip()]),
            "dataset_role": "lore_canon_foundation",
        },
        "features": {
            "char_length": len(text_body),
            "word_like_count": len(text_body.split()),
            "summary_chars": len(normalized),
            "timeline_signal": int(task_hints["has_timeline_signal"]),
        },
    }


def process_namuwiki(
    namuwiki_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    parquet_path = namuwiki_dir / "namuwiki_20210301_v3.parquet"
    if not parquet_path.exists():
        return

    parquet = pq.ParquetFile(parquet_path)
    row_id = 0
    for batch in parquet.iter_batches(batch_size=1024, columns=["title", "text", "contributors", "namespace"]):
        for row in batch.to_pylist():
            try:
                record = build_namuwiki_record(row=row, row_id=row_id)
            except Exception:
                stats.parse_errors += 1
                row_id += 1
                continue
            row_id += 1
            if record is None:
                continue
            write_record(record, unified_handle, module_handles, module_counts)
            stats.total_records += 1
            stats.namuwiki_records += 1


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
        "dataset": "NarrativeOS Knowledge Graph + Entity Normalized",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            "wikipedia_dir": str(Path(args.wikipedia_dir)),
            "namuwiki_dir": str(Path(args.namuwiki_dir)),
        },
        "records": {
            "total": stats.total_records,
            "wikipedia": stats.wikipedia_records,
            "namuwiki": stats.namuwiki_records,
            "parse_errors": stats.parse_errors,
        },
        "module_record_counts": dict(module_counts),
        "notes": {
            "role": "ontology_and_lore_foundation",
            "not_primary_narrative_dataset": True,
            "text_strategy": f"compact article summary capped at {MAX_TEXT_CHARS} chars per entry for retrieval/index efficiency",
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
    text = """# NarrativeOS Knowledge Graph + Entity Normalized Datasets

This foundation corpus combines:
- Korean Wikipedia Dataset for GPT2 August 2022
- namuwiki-extracted

This corpus is intended for ontology, entity linking, lore, canon, and graph foundation use-cases.

Output:
- unified.jsonl
- by_module/*.jsonl
- manifests/normalization_manifest.json
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    module_names = WIKIPEDIA_MODULES + NAMUWIKI_MODULES
    stats = Stats()
    module_counts: Counter[str] = Counter()

    unified_handle, module_handles, manifests_dir = write_outputs(output_dir, module_names)
    try:
        process_wikipedia(
            wikipedia_dir=Path(args.wikipedia_dir),
            unified_handle=unified_handle,
            module_handles=module_handles,
            module_counts=module_counts,
            stats=stats,
        )
        process_namuwiki(
            namuwiki_dir=Path(args.namuwiki_dir),
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
                "wikipedia_records": stats.wikipedia_records,
                "namuwiki_records": stats.namuwiki_records,
                "parse_errors": stats.parse_errors,
                "module_record_counts": dict(module_counts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()