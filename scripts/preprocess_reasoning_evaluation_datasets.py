from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BENCHMARK_MODULES = [
    "semantic_reasoning_eval",
    "contextual_reasoning",
    "retrieval_evaluation",
    "consistency_scoring",
]

KLUE_TASKS = ("nli", "re", "mrc", "sts")


@dataclass(slots=True)
class Stats:
    total_records: int = 0
    kodialogbench_records: int = 0
    klue_records: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize KoDialogBench and KLUE benchmark tasks for NarrativeOS reasoning/evaluation"
    )
    parser.add_argument(
        "--kodialogbench-dir",
        default="datasets/kodialogbench",
        help="Path to KoDialogBench repository root",
    )
    parser.add_argument(
        "--klue-dir",
        default="datasets/KLUE",
        help="Path to KLUE repository root",
    )
    parser.add_argument(
        "--output-dir",
        default="datasets/normalized_reasoning_eval",
        help="Output directory for normalized records",
    )
    return parser.parse_args()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def detect_language(text: str) -> str:
    return "ko" if re.search(r"[\uac00-\ud7a3]", text or "") else "unknown"


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


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


def format_dialogue(dialogue: Any) -> tuple[str, int]:
    if not isinstance(dialogue, list):
        return "", 0
    turns: list[str] = []
    for turn in dialogue:
        if not isinstance(turn, list) or len(turn) < 2:
            continue
        speaker = normalize_whitespace(str(turn[0] or "unknown"))
        utterance = normalize_whitespace(str(turn[1] or ""))
        if not utterance:
            continue
        turns.append(f"[{speaker}] {utterance}")
    return "\n".join(turns), len(turns)


def build_kodialogbench_record(item: dict[str, Any], source_file: Path, row_id: int) -> dict[str, Any] | None:
    dialogue_text, turn_count = format_dialogue(item.get("dialogue"))
    if not dialogue_text:
        return None

    options = item.get("options") if isinstance(item.get("options"), list) else []
    norm_options = [normalize_whitespace(str(opt or "")) for opt in options]
    norm_options = [opt for opt in norm_options if opt]

    answer_idx = item.get("answer_idx")
    answer_text = None
    if isinstance(answer_idx, int) and 0 <= answer_idx < len(norm_options):
        answer_text = norm_options[answer_idx]

    question = normalize_whitespace(str(item.get("question") or ""))
    target_speaker = normalize_whitespace(str(item.get("target_speaker") or ""))

    prompt = question or "다음 발화 또는 정답 선택지를 고르세요."
    option_block = "\n".join(f"- ({idx}) {opt}" for idx, opt in enumerate(norm_options))

    text_parts = [f"[dialogue]\n{dialogue_text}"]
    text_parts.append(f"[prompt] {prompt}")
    if target_speaker:
        text_parts.append(f"[target_speaker] {target_speaker}")
    if option_block:
        text_parts.append(f"[options]\n{option_block}")
    if answer_text:
        text_parts.append(f"[gold_answer] {answer_text}")

    text = "\n\n".join(text_parts)

    task_group = source_file.parts[-3] if len(source_file.parts) >= 3 else "unknown"
    subtask = source_file.parts[-2] if len(source_file.parts) >= 2 else "unknown"
    split_name = source_file.stem

    return {
        "record_id": f"kodialogbench:{task_group}:{subtask}:{split_name}:{row_id}",
        "source_dataset": "KoDialogBench",
        "language": detect_language(text),
        "module_targets": list(BENCHMARK_MODULES),
        "record_type": "conversation",
        "text": text,
        "source": {
            "split": split_name,
            "task_group": task_group,
            "subtask": subtask,
            "path": str(source_file),
        },
        "annotations": {
            "question": question or None,
            "target_speaker": target_speaker or None,
            "options": norm_options,
            "answer_idx": answer_idx if isinstance(answer_idx, int) else None,
            "answer_text": answer_text,
            "turn_count": turn_count,
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "turn_count": turn_count,
            "option_count": len(norm_options),
        },
    }


def process_kodialogbench(
    root_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
    task_counts: Counter[str],
) -> None:
    for jsonl_path in sorted(root_dir.glob("**/test.jsonl")):
        for row_id, item in enumerate(iter_jsonl(jsonl_path)):
            try:
                record = build_kodialogbench_record(item=item, source_file=jsonl_path, row_id=row_id)
            except Exception:
                stats.parse_errors += 1
                continue

            if record is None:
                continue
            write_record(record, unified_handle, module_handles, module_counts)
            stats.total_records += 1
            stats.kodialogbench_records += 1
            task_key = f"kodialogbench/{record['source']['task_group']}/{record['source']['subtask']}"
            task_counts[task_key] += 1


def build_klue_nli_record(item: dict[str, Any]) -> dict[str, Any] | None:
    guid = normalize_whitespace(str(item.get("guid") or ""))
    premise = normalize_whitespace(str(item.get("premise") or ""))
    hypothesis = normalize_whitespace(str(item.get("hypothesis") or ""))
    label = normalize_whitespace(str(item.get("gold_label") or ""))
    if not guid or not premise or not hypothesis:
        return None

    text = "\n".join([
        "[task] NLI (contradiction/entailment/neutral)",
        f"[premise] {premise}",
        f"[hypothesis] {hypothesis}",
        f"[gold_label] {label}",
    ])

    return {
        "record_id": f"klue:nli:{guid}",
        "source_dataset": "KLUE",
        "language": detect_language(text),
        "module_targets": list(BENCHMARK_MODULES),
        "record_type": "utterance_segment",
        "text": text,
        "source": {
            "split": "provided_train_or_dev",
            "task": "nli",
            "genre": item.get("genre"),
        },
        "annotations": {
            "task": "NLI",
            "premise": premise,
            "hypothesis": hypothesis,
            "gold_label": label,
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "label": label,
        },
    }


def build_klue_re_record(item: dict[str, Any]) -> dict[str, Any] | None:
    guid = normalize_whitespace(str(item.get("guid") or ""))
    sentence = normalize_whitespace(str(item.get("sentence") or ""))
    if not guid or not sentence:
        return None

    subject_entity = item.get("subject_entity") if isinstance(item.get("subject_entity"), dict) else {}
    object_entity = item.get("object_entity") if isinstance(item.get("object_entity"), dict) else {}

    subj_word = normalize_whitespace(str(subject_entity.get("word") or ""))
    obj_word = normalize_whitespace(str(object_entity.get("word") or ""))
    label = normalize_whitespace(str(item.get("label") or ""))

    text = "\n".join([
        "[task] Relation Extraction",
        f"[sentence] {sentence}",
        f"[subject] {subj_word}",
        f"[object] {obj_word}",
        f"[gold_relation] {label}",
    ])

    return {
        "record_id": f"klue:re:{guid}",
        "source_dataset": "KLUE",
        "language": detect_language(text),
        "module_targets": list(BENCHMARK_MODULES),
        "record_type": "event",
        "text": text,
        "source": {
            "split": "provided_train_or_dev",
            "task": "re",
            "source": item.get("source"),
        },
        "annotations": {
            "task": "RE",
            "sentence": sentence,
            "subject_entity": subject_entity,
            "object_entity": object_entity,
            "label": label,
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "has_relation": int(label != "no_relation"),
        },
    }


def build_klue_mrc_records(document: dict[str, Any], doc_idx: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    title = normalize_whitespace(str(document.get("title") or ""))
    paragraphs = document.get("paragraphs") if isinstance(document.get("paragraphs"), list) else []

    for p_idx, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, dict):
            continue
        context = normalize_whitespace(str(paragraph.get("context") or ""))
        qas = paragraph.get("qas") if isinstance(paragraph.get("qas"), list) else []
        if not context:
            continue

        for q_idx, qa in enumerate(qas):
            if not isinstance(qa, dict):
                continue
            guid = normalize_whitespace(str(qa.get("guid") or f"doc{doc_idx}_p{p_idx}_q{q_idx}"))
            question = normalize_whitespace(str(qa.get("question") or ""))
            if not question:
                continue

            answers = qa.get("answers") if isinstance(qa.get("answers"), list) else []
            answer_texts = [
                normalize_whitespace(str(answer.get("text") or ""))
                for answer in answers
                if isinstance(answer, dict)
            ]
            answer_texts = [item for item in answer_texts if item]

            text_parts = [
                "[task] Machine Reading Comprehension",
                f"[title] {title}" if title else "[title] (none)",
                f"[context] {context}",
                f"[question] {question}",
            ]
            if answer_texts:
                text_parts.append("[gold_answers] " + " | ".join(answer_texts))
            text = "\n".join(text_parts)

            records.append(
                {
                    "record_id": f"klue:mrc:{guid}",
                    "source_dataset": "KLUE",
                    "language": detect_language(text),
                    "module_targets": list(BENCHMARK_MODULES),
                    "record_type": "scene_fragment",
                    "text": text,
                    "source": {
                        "split": "provided_train_or_dev",
                        "task": "mrc",
                        "news_category": document.get("news_category"),
                        "doc_source": document.get("source"),
                    },
                    "annotations": {
                        "task": "MRC",
                        "title": title or None,
                        "question": question,
                        "answers": answer_texts,
                        "question_type": qa.get("question_type"),
                        "is_impossible": qa.get("is_impossible"),
                    },
                    "features": {
                        "char_length": len(text),
                        "word_like_count": len(text.split()),
                        "answer_count": len(answer_texts),
                    },
                }
            )

    return records


def build_klue_sts_record(item: dict[str, Any]) -> dict[str, Any] | None:
    guid = normalize_whitespace(str(item.get("guid") or ""))
    sent1 = normalize_whitespace(str(item.get("sentence1") or ""))
    sent2 = normalize_whitespace(str(item.get("sentence2") or ""))
    if not guid or not sent1 or not sent2:
        return None

    labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
    similarity = labels.get("label")
    binary_label = labels.get("binary-label")

    text = "\n".join([
        "[task] Semantic Textual Similarity",
        f"[sentence1] {sent1}",
        f"[sentence2] {sent2}",
        f"[similarity] {similarity}",
        f"[binary_similarity] {binary_label}",
    ])

    return {
        "record_id": f"klue:sts:{guid}",
        "source_dataset": "KLUE",
        "language": detect_language(text),
        "module_targets": list(BENCHMARK_MODULES),
        "record_type": "utterance_segment",
        "text": text,
        "source": {
            "split": "provided_train_or_dev",
            "task": "sts",
            "source": item.get("source"),
        },
        "annotations": {
            "task": "STS",
            "sentence1": sent1,
            "sentence2": sent2,
            "labels": labels,
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "similarity": similarity,
            "binary_similarity": binary_label,
        },
    }


def process_klue(
    klue_dir: Path,
    unified_handle,
    module_handles: dict[str, Any],
    module_counts: Counter[str],
    stats: Stats,
    task_counts: Counter[str],
) -> None:
    base = klue_dir / "klue_benchmark"

    # NLI
    for split in ("train", "dev"):
        path = base / "klue-nli-v1.1" / f"klue-nli-v1.1_{split}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            stats.parse_errors += 1
            continue
        if not isinstance(payload, list):
            continue

        for item in payload:
            try:
                record = build_klue_nli_record(item)
            except Exception:
                stats.parse_errors += 1
                continue
            if record is None:
                continue
            record["source"]["split"] = split
            write_record(record, unified_handle, module_handles, module_counts)
            stats.total_records += 1
            stats.klue_records += 1
            task_counts["klue/nli"] += 1

    # RE
    for split in ("train", "dev"):
        path = base / "klue-re-v1.1" / f"klue-re-v1.1_{split}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            stats.parse_errors += 1
            continue
        if not isinstance(payload, list):
            continue

        for item in payload:
            try:
                record = build_klue_re_record(item)
            except Exception:
                stats.parse_errors += 1
                continue
            if record is None:
                continue
            record["source"]["split"] = split
            write_record(record, unified_handle, module_handles, module_counts)
            stats.total_records += 1
            stats.klue_records += 1
            task_counts["klue/re"] += 1

    # MRC
    for split in ("train", "dev"):
        path = base / "klue-mrc-v1.1" / f"klue-mrc-v1.1_{split}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            stats.parse_errors += 1
            continue

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            continue

        for doc_idx, document in enumerate(data):
            try:
                records = build_klue_mrc_records(document, doc_idx)
            except Exception:
                stats.parse_errors += 1
                continue
            for record in records:
                record["source"]["split"] = split
                write_record(record, unified_handle, module_handles, module_counts)
                stats.total_records += 1
                stats.klue_records += 1
                task_counts["klue/mrc"] += 1

    # STS
    for split in ("train", "dev"):
        path = base / "klue-sts-v1.1" / f"klue-sts-v1.1_{split}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            stats.parse_errors += 1
            continue
        if not isinstance(payload, list):
            continue

        for item in payload:
            try:
                record = build_klue_sts_record(item)
            except Exception:
                stats.parse_errors += 1
                continue
            if record is None:
                continue
            record["source"]["split"] = split
            write_record(record, unified_handle, module_handles, module_counts)
            stats.total_records += 1
            stats.klue_records += 1
            task_counts["klue/sts"] += 1


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
    task_counts: Counter[str],
    args: argparse.Namespace,
) -> None:
    payload = {
        "dataset": "NarrativeOS Reasoning + Evaluation Normalized",
        "version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            "kodialogbench_dir": str(Path(args.kodialogbench_dir)),
            "klue_dir": str(Path(args.klue_dir)),
        },
        "records": {
            "total": stats.total_records,
            "kodialogbench": stats.kodialogbench_records,
            "klue": stats.klue_records,
            "parse_errors": stats.parse_errors,
        },
        "task_record_counts": dict(task_counts),
        "module_record_counts": dict(module_counts),
        "notes": {
            "role": "evaluation_benchmark",
            "not_primary_training_dataset": True,
            "klue_tasks_used": list(KLUE_TASKS),
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
    text = """# NarrativeOS Reasoning + Evaluation Normalized Datasets

This benchmark corpus combines:
- KoDialogBench
- KLUE tasks: NLI, RE, MRC, STS

This corpus is for evaluation benchmark usage, not primary model training.

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
    task_counts: Counter[str] = Counter()

    unified_handle, module_handles, manifests_dir = write_outputs(output_dir, BENCHMARK_MODULES)
    try:
        process_kodialogbench(
            root_dir=Path(args.kodialogbench_dir),
            unified_handle=unified_handle,
            module_handles=module_handles,
            module_counts=module_counts,
            stats=stats,
            task_counts=task_counts,
        )
        process_klue(
            klue_dir=Path(args.klue_dir),
            unified_handle=unified_handle,
            module_handles=module_handles,
            module_counts=module_counts,
            stats=stats,
            task_counts=task_counts,
        )
    finally:
        unified_handle.close()
        for handle in module_handles.values():
            handle.close()

    write_manifest(
        manifests_dir=manifests_dir,
        stats=stats,
        module_counts=module_counts,
        task_counts=task_counts,
        args=args,
    )
    write_readme(output_dir)

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(output_dir),
                "records_total": stats.total_records,
                "kodialogbench_records": stats.kodialogbench_records,
                "klue_records": stats.klue_records,
                "parse_errors": stats.parse_errors,
                "task_record_counts": dict(task_counts),
                "module_record_counts": dict(module_counts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
