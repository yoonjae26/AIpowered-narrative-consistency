from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


KTDD_MODULES = [
    "dialogue_consistency",
    "conversational_memory",
    "multi_agent_realism",
    "interaction_pacing",
]

KOMUCHAT_MODULES = [
    "modern_dialogue_realism",
    "critic_agent",
    "semantic_validator",
    "character_personality",
]


@dataclass(slots=True)
class Stats:
    total_records: int = 0
    ktdd_records: int = 0
    komuchat_records: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize K-TDD and KOMUChat for NarrativeOS dialogue/interaction modules"
    )
    parser.add_argument(
        "--ktdd-dir",
        default="datasets/020.주제별텍스트일상 대화데이터",
        help="Path to K-TDD dataset root",
    )
    parser.add_argument(
        "--komuchat-dir",
        default="/home/hong/.cache/huggingface/hub/datasets--4n3mone--komuchat/snapshots/bfccf8a6302bbd44e133bd91479b6c3ef0f79942",
        help="Path to KOMUChat snapshot root",
    )
    parser.add_argument(
        "--output-dir",
        default="datasets/normalized_dialogue_interaction",
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


def infer_ktdd_split(zip_path: Path) -> str:
    path_str = str(zip_path)
    if "2.Validation" in path_str:
        return "validation"
    return "train"


def iter_ktdd_label_zips(ktdd_dir: Path) -> list[Path]:
    # Keep only label-data archives; source-data archives are not required for normalization.
    zips = [
        path
        for path in sorted(ktdd_dir.glob("**/*.zip"))
        if any("라벨링데이터" in part for part in path.parts)
    ]
    return zips


def build_ktdd_record(payload: dict[str, Any], zip_path: Path, json_name: str) -> dict[str, Any] | None:
    info_list = payload.get("info") if isinstance(payload.get("info"), list) else []
    if not info_list:
        return None

    info = info_list[0] if isinstance(info_list[0], dict) else {}
    annotations = info.get("annotations") if isinstance(info.get("annotations"), dict) else {}
    lines = annotations.get("lines") if isinstance(annotations.get("lines"), list) else []

    turns: list[dict[str, Any]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        speaker = line.get("speaker") if isinstance(line.get("speaker"), dict) else {}
        norm_text = normalize_whitespace(str(line.get("norm_text") or ""))
        if not norm_text:
            norm_text = normalize_whitespace(str(line.get("text") or ""))
        if not norm_text:
            continue

        turns.append(
            {
                "turn_id": line.get("id"),
                "speaker_id": normalize_whitespace(str(speaker.get("id") or "unknown")),
                "speaker_sex": normalize_whitespace(str(speaker.get("sex") or "unknown")),
                "speaker_age": normalize_whitespace(str(speaker.get("age") or "unknown")),
                "speech_act": normalize_whitespace(str(line.get("speechAct") or "")),
                "text": norm_text,
            }
        )

    if not turns:
        return None

    dialogue_text = "\n".join(
        f"[{turn['speaker_id']}] {turn['text']}" for turn in turns
    )
    unique_speakers = sorted({turn["speaker_id"] for turn in turns if turn["speaker_id"]})

    dataset = payload.get("dataset") if isinstance(payload.get("dataset"), dict) else {}
    split_name = infer_ktdd_split(zip_path)
    base_id = Path(json_name).stem

    return {
        "record_id": f"ktdd:{split_name}:{base_id}",
        "source_dataset": "K-TDD",
        "language": detect_language(dialogue_text),
        "module_targets": list(KTDD_MODULES),
        "record_type": "dialogue_session",
        "text": dialogue_text,
        "source": {
            "split": split_name,
            "zip_file": zip_path.name,
            "file_name": str(info.get("filename") or json_name),
            "media_name": info.get("medianame"),
            "media_type": info.get("mediatype"),
            "category": info.get("category"),
            "dataset_category": dataset.get("category"),
            "dataset_name": dataset.get("name"),
        },
        "annotations": {
            "title": info.get("title"),
            "subject": annotations.get("subject"),
            "speaker_type": annotations.get("speaker_type"),
            "turn_count": len(turns),
            "speakers": unique_speakers,
            "turns": turns,
        },
        "features": {
            "char_length": len(dialogue_text),
            "word_like_count": len(dialogue_text.split()),
            "turn_count": len(turns),
            "speaker_count": len(unique_speakers),
            "question_turns": sum(1 for turn in turns if "?" in turn["text"]),
        },
    }


def process_ktdd(
    ktdd_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    for zip_path in iter_ktdd_label_zips(ktdd_dir):
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for json_name in zf.namelist():
                    if not json_name.lower().endswith(".json"):
                        continue
                    try:
                        payload = json.loads(zf.read(json_name).decode("utf-8"))
                        record = build_ktdd_record(payload=payload, zip_path=zip_path, json_name=json_name)
                    except Exception:
                        stats.parse_errors += 1
                        continue

                    if record is None:
                        continue
                    write_record(record, unified_handle, module_handles, module_counts)
                    stats.total_records += 1
                    stats.ktdd_records += 1
        except Exception:
            stats.parse_errors += 1


def build_komuchat_record(
    row: dict[str, Any],
    split_name: str,
    row_id: int,
    parquet_file: str,
) -> dict[str, Any] | None:
    question = normalize_whitespace(str(row.get("Q") or ""))
    answer = normalize_whitespace(str(row.get("A") or ""))
    if not question or not answer:
        return None

    tag = normalize_whitespace(str(row.get("tag") or ""))
    src = normalize_whitespace(str(row.get("src") or ""))
    text = f"[user] {question}\n[assistant] {answer}"

    return {
        "record_id": f"komuchat:{split_name}:{row_id}",
        "source_dataset": "KOMUChat",
        "language": detect_language(text),
        "module_targets": list(KOMUCHAT_MODULES),
        "record_type": "conversation",
        "text": text,
        "source": {
            "split": split_name,
            "parquet_file": parquet_file,
            "tag": tag or None,
            "src": src or None,
        },
        "annotations": {
            "tag": tag or None,
            "src": src or None,
            "question": question,
            "answer": answer,
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "question_length": len(question),
            "answer_length": len(answer),
            "question_mark_signal": int("?" in question),
        },
    }


def process_komuchat(
    komuchat_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    data_dir = komuchat_dir / "data"
    if not data_dir.exists():
        return

    row_counter = 0
    parquet_files = sorted(data_dir.glob("*.parquet"))
    for parquet_path in parquet_files:
        split_name = "validation" if "validation" in parquet_path.name else "train"
        parquet = pq.ParquetFile(parquet_path)
        for batch in parquet.iter_batches(batch_size=1024, columns=["tag", "Q", "A", "src"]):
            for row in batch.to_pylist():
                try:
                    record = build_komuchat_record(
                        row=row,
                        split_name=split_name,
                        row_id=row_counter,
                        parquet_file=parquet_path.name,
                    )
                except Exception:
                    stats.parse_errors += 1
                    row_counter += 1
                    continue

                row_counter += 1
                if record is None:
                    continue

                write_record(record, unified_handle, module_handles, module_counts)
                stats.total_records += 1
                stats.komuchat_records += 1


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
        "dataset": "NarrativeOS Dialogue + Interaction Normalized",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            "ktdd_dir": str(Path(args.ktdd_dir)),
            "komuchat_dir": str(Path(args.komuchat_dir)),
        },
        "records": {
            "total": stats.total_records,
            "ktdd": stats.ktdd_records,
            "komuchat": stats.komuchat_records,
            "parse_errors": stats.parse_errors,
        },
        "module_record_counts": dict(module_counts),
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
    text = """# NarrativeOS Dialogue + Interaction Normalized Datasets

This corpus combines:
- K-TDD (Topic-specific Daily Dialogue Data)
- KOMUChat

Output:
- unified.jsonl
- by_module/*.jsonl
- manifests/normalization_manifest.json
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    module_names = KTDD_MODULES + KOMUCHAT_MODULES
    stats = Stats()
    module_counts: Counter[str] = Counter()

    unified_handle, module_handles, manifests_dir = write_outputs(output_dir, module_names)
    try:
        process_ktdd(
            ktdd_dir=Path(args.ktdd_dir),
            unified_handle=unified_handle,
            module_handles=module_handles,
            module_counts=module_counts,
            stats=stats,
        )
        process_komuchat(
            komuchat_dir=Path(args.komuchat_dir),
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
                "ktdd_records": stats.ktdd_records,
                "komuchat_records": stats.komuchat_records,
                "parse_errors": stats.parse_errors,
                "module_record_counts": dict(module_counts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
