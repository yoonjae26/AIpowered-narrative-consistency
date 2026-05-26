from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


KMI_MODULES = [
    "belief_evolution",
    "trauma_persistence",
    "emotional_cognition",
    "personality_modeling",
]


@dataclass(slots=True)
class Stats:
    total_records: int = 0
    kmi_records: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize KMI for NarrativeOS specialized advanced evolution modules"
    )
    parser.add_argument(
        "--kmi-path",
        default="datasets/KMI/kmi.json",
        help="Path to KMI JSON file",
    )
    parser.add_argument(
        "--output-dir",
        default="datasets/normalized_specialized_kmi",
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


def format_dialogue_turns(dialogue: list[dict[str, Any]]) -> tuple[list[str], list[str], int, int]:
    lines: list[str] = []
    therapist_labels: list[str] = []
    therapist_turns = 0
    client_turns = 0

    for turn in dialogue:
        if not isinstance(turn, dict):
            continue

        role = normalize_whitespace(str(turn.get("role") or "Unknown"))
        utterance_ko = normalize_whitespace(str(turn.get("utterance_ko") or ""))
        if not utterance_ko:
            utterance_ko = normalize_whitespace(str(turn.get("utterance_en") or ""))
        if not utterance_ko:
            continue

        lines.append(f"[{role}] {utterance_ko}")

        if role.lower() == "therapist":
            therapist_turns += 1
            technique = normalize_whitespace(str(turn.get("label") or ""))
            if technique:
                therapist_labels.append(technique)
        elif role.lower() == "client":
            client_turns += 1

    return lines, therapist_labels, therapist_turns, client_turns


def build_kmi_record(item: dict[str, Any]) -> dict[str, Any] | None:
    dialogue = item.get("dialogue") if isinstance(item.get("dialogue"), list) else []
    if not dialogue:
        return None

    lines, therapist_labels, therapist_turns, client_turns = format_dialogue_turns(dialogue)
    if not lines:
        return None

    category_ko = normalize_whitespace(str(item.get("category_ko") or ""))
    category_en = normalize_whitespace(str(item.get("category_en") or ""))
    dialogue_id = item.get("id")

    text_parts = []
    if category_ko:
        text_parts.append(f"[category_ko] {category_ko}")
    if category_en:
        text_parts.append(f"[category_en] {category_en}")
    text_parts.append("[dialogue]\n" + "\n".join(lines))
    text = "\n\n".join(text_parts)

    technique_counts = Counter(therapist_labels)

    return {
        "record_id": f"kmi:{dialogue_id}",
        "source_dataset": "KMI",
        "language": detect_language(text),
        "module_targets": list(KMI_MODULES),
        "record_type": "dialogue_session",
        "text": text,
        "source": {
            "split": "all",
            "dialogue_id": dialogue_id,
            "category_ko": category_ko or None,
            "category_en": category_en or None,
        },
        "annotations": {
            "therapist_labels": therapist_labels,
            "therapist_label_counts": dict(technique_counts),
            "turn_count": len(lines),
            "therapist_turns": therapist_turns,
            "client_turns": client_turns,
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "turn_count": len(lines),
            "therapist_turns": therapist_turns,
            "client_turns": client_turns,
            "unique_techniques": len(technique_counts),
        },
    }


def process_kmi(
    kmi_path: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    if not kmi_path.exists():
        return

    payload = json.loads(kmi_path.read_text(encoding="utf-8"))
    items = payload if isinstance(payload, list) else []

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            record = build_kmi_record(item)
        except Exception:
            stats.parse_errors += 1
            continue

        if record is None:
            continue
        write_record(record, unified_handle, module_handles, module_counts)
        stats.total_records += 1
        stats.kmi_records += 1


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
        "dataset": "NarrativeOS Specialized KMI Normalized",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            "kmi_path": str(Path(args.kmi_path)),
        },
        "records": {
            "total": stats.total_records,
            "kmi": stats.kmi_records,
            "parse_errors": stats.parse_errors,
        },
        "module_record_counts": dict(module_counts),
        "notes": {
            "role": "pkbd_evolution_support",
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
    text = """# NarrativeOS Specialized KMI Normalized Dataset

This corpus contains:
- KMI (Korean Motivational Interviewing style dialogues)

This corpus is intended for P, K, B, D evolution system support:
- belief_evolution
- trauma_persistence
- emotional_cognition
- personality_modeling

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

    unified_handle, module_handles, manifests_dir = write_outputs(output_dir, KMI_MODULES)
    try:
        process_kmi(
            kmi_path=Path(args.kmi_path),
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
                "kmi_records": stats.kmi_records,
                "parse_errors": stats.parse_errors,
                "module_record_counts": dict(module_counts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
