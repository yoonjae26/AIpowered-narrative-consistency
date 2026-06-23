from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


AIHUB_MODULES = [
    "emotional_mismatch",
    "semantic_validator",
    "character_drift",
    "dialogue_realism",
]

KEMDY_MODULES = [
    "emotion_tracking",
    "emotional_memory",
    "semantic_validator",
    "character_cognition",
    "emotional_state_transitions",
    "subtle_emotional_contradiction",
    "affective_reasoning",
]


@dataclass(slots=True)
class Stats:
    total_records: int = 0
    aihub_records: int = 0
    kemdy_records: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize AIHub Emotional Dialogue and KEMDy20 for NarrativeOS")
    parser.add_argument(
        "--aihub-dir",
        default="datasets/018.감성대화",
        help="Path to AIHub Emotional Dialogue Corpus root",
    )
    parser.add_argument(
        "--kemdy-dir",
        default="datasets/Multi-Still_ETRI/KEMDy20",
        help="Path to KEMDy20 root",
    )
    parser.add_argument(
        "--output-dir",
        default="datasets/normalized_emotional",
        help="Output directory for normalized records",
    )
    return parser.parse_args()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def detect_language(text: str) -> str:
    return "ko" if re.search(r"[\uac00-\ud7a3]", text or "") else "unknown"


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def extract_aihub_json_from_zip(zip_path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        target = [name for name in zf.namelist() if name.lower().endswith(".json")]
        if not target:
            return []
        data = zf.read(target[0]).decode("utf-8")
        payload = json.loads(data)
        return payload if isinstance(payload, list) else []


def build_aihub_record(item: dict[str, Any], split_name: str) -> dict[str, Any] | None:
    profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
    talk = item.get("talk") if isinstance(item.get("talk"), dict) else {}
    talk_id = ((talk.get("id") or {}).get("talk-id") if isinstance(talk.get("id"), dict) else None) or ""
    contents = talk.get("content") if isinstance(talk.get("content"), dict) else {}

    ordered_turn_keys = sorted(
        [key for key in contents.keys() if isinstance(key, str) and re.match(r"^[A-Z]{2}\d{2}$", key)],
        key=lambda key: (key[:2], int(key[2:])),
    )
    turns: list[dict[str, str]] = []
    for key in ordered_turn_keys:
        text = normalize_whitespace(str(contents.get(key) or ""))
        if not text:
            continue
        speaker = "human" if key.startswith("HS") else ("system" if key.startswith("SS") else "unknown")
        turns.append({"turn_id": key, "speaker": speaker, "text": text})

    if not turns:
        return None

    merged = " ".join(f"[{turn['speaker']}] {turn['text']}" for turn in turns)
    emotion = profile.get("emotion") if isinstance(profile.get("emotion"), dict) else {}
    persona = profile.get("persona") if isinstance(profile.get("persona"), dict) else {}

    return {
        "record_id": f"aihub_emodialog:{talk_id}",
        "source_dataset": "AIHub Emotional Dialogue Corpus",
        "language": detect_language(merged),
        "module_targets": list(AIHUB_MODULES),
        "record_type": "dialogue_session",
        "text": merged,
        "source": {
            "split": split_name,
            "persona_id": profile.get("persona-id"),
            "talk_id": talk_id,
            "persona_code": persona.get("persona-id"),
            "situation_codes": emotion.get("situation", []),
        },
        "annotations": {
            "emotion_code": emotion.get("type"),
            "emotion_id": emotion.get("emotion-id"),
            "turn_count": len(turns),
            "human_turns": sum(1 for turn in turns if turn["speaker"] == "human"),
            "system_turns": sum(1 for turn in turns if turn["speaker"] == "system"),
            "turns": turns,
        },
        "features": {
            "char_length": len(merged),
            "word_like_count": len(merged.split()),
            "turn_count": len(turns),
            "dialogue_realism_signal": sum(1 for turn in turns if "?" in turn["text"] or "!" in turn["text"]),
        },
    }


def process_aihub(
    aihub_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    zip_specs = [
        ("train", aihub_dir / "Training_221115_add" / "라벨링데이터" / "감성대화말뭉치(최종데이터)_Training.zip"),
        ("validation", aihub_dir / "Validation_221115_add" / "라벨링데이터" / "감성대화말뭉치(최종데이터)_Validation.zip"),
    ]

    for split_name, zip_path in zip_specs:
        if not zip_path.exists():
            continue
        for item in extract_aihub_json_from_zip(zip_path):
            try:
                record = build_aihub_record(item, split_name=split_name)
            except Exception:
                stats.parse_errors += 1
                continue
            if record is None:
                continue
            write_record(record, unified_handle, module_handles, module_counts)
            stats.total_records += 1
            stats.aihub_records += 1


def read_kemdy_text(transcript_path: Path) -> str:
    if not transcript_path.exists():
        return ""
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            raw = transcript_path.read_text(encoding=encoding)
            text = normalize_whitespace(raw)
            text = re.sub(r"\b[a-zA-Z]/", "", text)
            text = normalize_whitespace(text)
            return text
        except Exception:
            continue
    return ""


def evaluate_majority(emotions: list[str]) -> str | None:
    cleaned = [normalize_whitespace(item).lower() for item in emotions if normalize_whitespace(item)]
    if not cleaned:
        return None
    return Counter(cleaned).most_common(1)[0][0]


def build_kemdy_record(
    session_name: str,
    row: list[str],
    transcript_root: Path,
    split_name: str,
) -> dict[str, Any] | None:
    if len(row) < 7:
        return None

    segment_id = normalize_whitespace(row[3])
    if not segment_id:
        return None

    start_sec = parse_float(row[1])
    end_sec = parse_float(row[2])

    total_emotion = normalize_whitespace(row[4]).lower()
    emotion_votes: list[str] = [total_emotion] if total_emotion else []
    valence_values: list[float] = []
    arousal_values: list[float] = []

    total_valence = parse_float(row[5])
    total_arousal = parse_float(row[6])
    if total_valence is not None:
        valence_values.append(total_valence)
    if total_arousal is not None:
        arousal_values.append(total_arousal)

    index = 7
    while index + 2 < len(row):
        emo = normalize_whitespace(row[index]).lower()
        val = parse_float(row[index + 1])
        aro = parse_float(row[index + 2])
        if emo:
            emotion_votes.append(emo)
        if val is not None:
            valence_values.append(val)
        if aro is not None:
            arousal_values.append(aro)
        index += 3

    majority_emotion = evaluate_majority(emotion_votes)
    mean_valence = round(sum(valence_values) / len(valence_values), 4) if valence_values else None
    mean_arousal = round(sum(arousal_values) / len(arousal_values), 4) if arousal_values else None

    transcript_path = transcript_root / session_name / f"{segment_id}.txt"
    text = read_kemdy_text(transcript_path)
    if not text:
        return None

    return {
        "record_id": f"kemdy20:{segment_id}",
        "source_dataset": "KEMDy20",
        "language": detect_language(text),
        "module_targets": list(KEMDY_MODULES),
        "record_type": "utterance_segment",
        "text": text,
        "source": {
            "split": split_name,
            "session": session_name,
            "segment_id": segment_id,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "transcript_path": str(transcript_path),
        },
        "annotations": {
            "total_emotion": total_emotion or None,
            "majority_emotion": majority_emotion,
            "emotion_votes": [vote for vote in emotion_votes if vote],
            "mean_valence": mean_valence,
            "mean_arousal": mean_arousal,
            "rater_count": max(0, (len(row) - 4) // 3),
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "mean_valence": mean_valence,
            "mean_arousal": mean_arousal,
            "emotion_vote_count": len([vote for vote in emotion_votes if vote]),
        },
    }


def process_kemdy(
    kemdy_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
) -> None:
    ann_dir = kemdy_dir / "annotation"
    transcript_root = kemdy_dir / "wav"
    if not ann_dir.exists() or not transcript_root.exists():
        return

    for csv_path in sorted(ann_dir.glob("Sess*_eval.csv")):
        split_name = "train"
        if "Sess03" in csv_path.name:
            split_name = "validation"
        session_name = csv_path.stem.split("_", 1)[0].replace("eval", "")
        if not session_name.startswith("Sess"):
            session_name = session_name or "SessionUnknown"

        with csv_path.open("r", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            for row_index, row in enumerate(reader):
                if row_index < 2:
                    continue
                if not row:
                    continue
                if not normalize_whitespace(row[0]).isdigit():
                    continue
                try:
                    record = build_kemdy_record(
                        session_name=session_name.replace("Sess", "Session"),
                        row=row,
                        transcript_root=transcript_root,
                        split_name=split_name,
                    )
                except Exception:
                    stats.parse_errors += 1
                    continue
                if record is None:
                    continue
                write_record(record, unified_handle, module_handles, module_counts)
                stats.total_records += 1
                stats.kemdy_records += 1


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
        "dataset": "NarrativeOS Emotional+Character Normalized",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            "aihub_dir": str(Path(args.aihub_dir)),
            "kemdy_dir": str(Path(args.kemdy_dir)),
        },
        "records": {
            "total": stats.total_records,
            "aihub_emotional_dialogue": stats.aihub_records,
            "kemdy20": stats.kemdy_records,
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
    text = """# NarrativeOS Emotional + Character Normalized Datasets

This corpus combines:
- AIHub Emotional Dialogue Corpus
- KEMDy20

Output:
- unified.jsonl
- by_module/*.jsonl
- manifests/normalization_manifest.json
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    module_names = AIHUB_MODULES + KEMDY_MODULES
    stats = Stats()
    module_counts: Counter[str] = Counter()

    unified_handle, module_handles, manifests_dir = write_outputs(output_dir, module_names)
    try:
        process_aihub(
            aihub_dir=Path(args.aihub_dir),
            unified_handle=unified_handle,
            module_handles=module_handles,
            module_counts=module_counts,
            stats=stats,
        )
        process_kemdy(
            kemdy_dir=Path(args.kemdy_dir),
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

    print(json.dumps(
        {
            "status": "ok",
            "output_dir": str(output_dir),
            "records_total": stats.total_records,
            "aihub_records": stats.aihub_records,
            "kemdy_records": stats.kemdy_records,
            "parse_errors": stats.parse_errors,
            "module_record_counts": dict(module_counts),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
