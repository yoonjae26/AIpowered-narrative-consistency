from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


KOCONOVEL_MODULES = [
    "semantic_validator",
    "drift_detector",
    "timeline_engine",
    "retrieval",
    "multi_agent_analysis",
]

KOREAN_WEBNOVEL_MODULES = [
    "character_cognition",
    "relationship_graph",
    "pacing_analysis",
    "emotional_progression",
    "canon_tracking",
]


@dataclass(slots=True)
class NormalizationStats:
    records_total: int = 0
    koconovel_records: int = 0
    korean_webnovel_records: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize KoCoNovel and Korean Web Novel Corpus for NarrativeOS")
    parser.add_argument(
        "--koconovel-dir",
        default="datasets/KoCoNovel",
        help="Path to KoCoNovel root directory",
    )
    parser.add_argument(
        "--korean-corpus-dir",
        default="datasets/sample_re/sample",
        help="Path to Korean Web Novel Corpus root directory",
    )
    parser.add_argument(
        "--output-dir",
        default="datasets/normalized",
        help="Output directory for normalized dataset",
    )
    return parser.parse_args()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def detect_language(text: str) -> str:
    if re.search(r"[\uac00-\ud7a3]", text or ""):
        return "ko"
    return "unknown"


def safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def safe_load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_koconovel_index(root: Path) -> dict[str, dict[str, str]]:
    csv_path = root / "list_of_novels.csv"
    index: dict[str, dict[str, str]] = {}
    if not csv_path.exists():
        return index

    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            novel_id = (row.get("ID") or "").strip()
            if novel_id:
                index[novel_id] = {
                    "korean_title": (row.get("Korean Title") or "").strip(),
                    "translated_title": (row.get("Translated Title") or "").strip(),
                    "romanized_title": (row.get("Yale Romanization of Title") or "").strip(),
                    "romanized_author": (row.get("Romanization of Author") or "").strip(),
                }
    return index


def summarize_coref_annotations(coref_item: dict[str, Any]) -> dict[str, Any]:
    def _flatten_chains(chains: Any) -> tuple[int, list[str]]:
        if not isinstance(chains, list):
            return 0, []
        mentions = 0
        entity_ids: list[str] = []
        for chain in chains:
            if not isinstance(chain, list):
                continue
            for mention in chain:
                if not isinstance(mention, list) or len(mention) < 4:
                    continue
                mentions += 1
                entity_ids.append(str(mention[3]))
        return mentions, entity_ids

    options = [
        "omniscent_separate",
        "omniscent_overlapped",
        "reader_separate",
        "reader_overlapped",
    ]
    chain_counts: dict[str, int] = {}
    mention_counts: dict[str, int] = {}
    entity_counter: Counter[str] = Counter()

    for key in options:
        chains = coref_item.get(key, [])
        chain_counts[key] = len(chains) if isinstance(chains, list) else 0
        mentions, entity_ids = _flatten_chains(chains)
        mention_counts[key] = mentions
        entity_counter.update(entity_ids)

    speakers = coref_item.get("speakers", [])
    speaker_segments = 0
    unique_speakers: set[str] = set()
    if isinstance(speakers, list):
        for group in speakers:
            if not isinstance(group, list):
                continue
            for segment in group:
                if not isinstance(segment, list) or len(segment) < 3:
                    continue
                speaker_segments += 1
                unique_speakers.add(str(segment[2]))

    return {
        "chain_counts": chain_counts,
        "mention_counts": mention_counts,
        "speaker_segments": speaker_segments,
        "unique_speaker_labels": sorted(unique_speakers),
        "top_entity_labels": [item[0] for item in entity_counter.most_common(10)],
    }


def build_koconovel_record(
    novel_id: str,
    novel_dir_name: str,
    text_item: dict[str, Any],
    coref_item: dict[str, Any],
    novel_meta: dict[str, str],
) -> dict[str, Any]:
    doc_id = str(text_item.get("doc_id") or "")
    text = normalize_whitespace(str(text_item.get("text") or ""))
    coref_summary = summarize_coref_annotations(coref_item)

    doc_order = 0
    if "_" in doc_id:
        try:
            doc_order = int(doc_id.rsplit("_", 1)[-1])
        except ValueError:
            doc_order = 0

    return {
        "record_id": f"koconovel:{novel_id}:{doc_id}",
        "source_dataset": "KoCoNovel",
        "language": detect_language(text),
        "module_targets": list(KOCONOVEL_MODULES),
        "record_type": "scene_fragment",
        "text": text,
        "source": {
            "novel_id": novel_id,
            "novel_dir": novel_dir_name,
            "doc_id": doc_id,
            "doc_order": doc_order,
            "korean_title": novel_meta.get("korean_title", ""),
            "translated_title": novel_meta.get("translated_title", ""),
            "romanized_title": novel_meta.get("romanized_title", ""),
            "romanized_author": novel_meta.get("romanized_author", ""),
        },
        "annotations": {
            "coreference": coref_summary,
            "has_speaker_labels": coref_summary["speaker_segments"] > 0,
        },
        "features": {
            "char_length": len(text),
            "word_like_count": len(text.split()),
            "quote_count": text.count('"') + text.count("\u201c") + text.count("\u201d"),
        },
    }


def process_koconovel(
    root: Path,
    writers: dict[str, Any],
    module_writers: dict[str, Any],
    stats: NormalizationStats,
    module_counts: Counter[str],
) -> None:
    index = load_koconovel_index(root)
    jsonl_root = root / "data" / "jsonl"
    if not jsonl_root.exists():
        return

    for novel_dir in sorted(jsonl_root.iterdir()):
        if not novel_dir.is_dir():
            continue

        novel_dir_name = novel_dir.name
        novel_id = novel_dir_name.split("_", 1)[0]
        novel_meta = index.get(novel_id, {})
        text_path = novel_dir / "text.jsonl"
        coref_path = novel_dir / "coref.jsonl"
        if not text_path.exists() or not coref_path.exists():
            continue

        coref_map: dict[str, dict[str, Any]] = {}
        for item in safe_load_jsonl(coref_path):
            coref_map[str(item.get("doc_id") or "")] = item

        for text_item in safe_load_jsonl(text_path):
            doc_id = str(text_item.get("doc_id") or "")
            coref_item = coref_map.get(doc_id, {})
            try:
                record = build_koconovel_record(novel_id, novel_dir_name, text_item, coref_item, novel_meta)
            except Exception:
                stats.parse_errors += 1
                continue
            write_record(record, writers, module_writers, module_counts)
            stats.records_total += 1
            stats.koconovel_records += 1


def build_korean_webnovel_record(
    corpus_id: str,
    chunk_file_name: str,
    paragraph_index: int,
    paragraph: dict[str, Any],
    corpus_info: dict[str, Any],
    corpus_stats: dict[str, Any],
) -> dict[str, Any]:
    para_id = str(paragraph.get("id") or f"{corpus_id}.{paragraph_index + 1}")
    sentences = paragraph.get("sentences") if isinstance(paragraph.get("sentences"), list) else []

    normalized_sentences: list[str] = []
    sentence_ids: list[str] = []
    noise_values: list[float] = []

    for sentence in sentences:
        if not isinstance(sentence, dict):
            continue
        sent_text = normalize_whitespace(str(sentence.get("text") or ""))
        if not sent_text:
            continue
        normalized_sentences.append(sent_text)
        sentence_ids.append(str(sentence.get("id") or ""))
        try:
            noise_values.append(float(sentence.get("noise_ratio") or 0.0))
        except (TypeError, ValueError):
            noise_values.append(0.0)

    paragraph_text = " ".join(normalized_sentences)
    para_info = paragraph.get("info") if isinstance(paragraph.get("info"), dict) else {}
    author = para_info.get("author") if isinstance(para_info.get("author"), dict) else {}

    avg_noise = round(sum(noise_values) / len(noise_values), 6) if noise_values else 0.0

    return {
        "record_id": f"korean_webnovel:{corpus_id}:{para_id}",
        "source_dataset": "Korean Web Novel Corpus",
        "language": detect_language(paragraph_text),
        "module_targets": list(KOREAN_WEBNOVEL_MODULES),
        "record_type": "paragraph",
        "text": paragraph_text,
        "source": {
            "corpus_id": corpus_id,
            "chunk_file": chunk_file_name,
            "paragraph_id": para_id,
            "paragraph_index": paragraph_index,
            "sentence_ids": sentence_ids,
            "kdc": str(para_info.get("kdc") or corpus_info.get("kdc") or ""),
            "class": para_info.get("class"),
            "published_year": para_info.get("published_year"),
            "author_birth_year": author.get("birth_year"),
            "author_write_age": author.get("write_age"),
            "author_jobs": [normalize_whitespace(str(item)) for item in (author.get("jobs") or []) if str(item).strip()],
        },
        "annotations": {
            "sentence_count": len(normalized_sentences),
            "avg_sentence_noise_ratio": avg_noise,
            "corpus_stat_avg_sentence_per_paragraph": corpus_stats.get("average_sentence_count_per_paragraph"),
            "corpus_stat_avg_char_per_sentence": corpus_stats.get("average_char_count_per_sentence"),
        },
        "features": {
            "char_length": len(paragraph_text),
            "word_like_count": len(paragraph_text.split()),
            "sentence_count": len(normalized_sentences),
            "avg_sentence_noise_ratio": avg_noise,
        },
    }


def process_korean_webnovel(
    root: Path,
    writers: dict[str, Any],
    module_writers: dict[str, Any],
    stats: NormalizationStats,
    module_counts: Counter[str],
) -> None:
    labeled_root = root / "라벨링데이터"
    if not labeled_root.exists():
        return

    for corpus_dir in sorted(labeled_root.iterdir()):
        if not corpus_dir.is_dir():
            continue

        info_files = sorted(corpus_dir.glob("*_INFO.json"))
        corpus_info_payload = safe_load_json(info_files[0]) if info_files else {}
        corpus_id = str((corpus_info_payload or {}).get("id") or corpus_dir.name)
        corpus_info = dict((corpus_info_payload or {}).get("info") or {})
        corpus_stats = dict((corpus_info_payload or {}).get("statistics") or {})

        for text_path in sorted(corpus_dir.glob("*_TEXT_*.json")):
            payload = safe_load_json(text_path)
            if payload is None:
                stats.parse_errors += 1
                continue
            paragraphs = payload.get("paragraphs") if isinstance(payload.get("paragraphs"), list) else []
            for idx, paragraph in enumerate(paragraphs):
                if not isinstance(paragraph, dict):
                    continue
                try:
                    record = build_korean_webnovel_record(
                        corpus_id=corpus_id,
                        chunk_file_name=text_path.name,
                        paragraph_index=idx,
                        paragraph=paragraph,
                        corpus_info=corpus_info,
                        corpus_stats=corpus_stats,
                    )
                except Exception:
                    stats.parse_errors += 1
                    continue

                if not record["text"]:
                    continue

                write_record(record, writers, module_writers, module_counts)
                stats.records_total += 1
                stats.korean_webnovel_records += 1


def write_record(
    record: dict[str, Any],
    writers: dict[str, Any],
    module_writers: dict[str, Any],
    module_counts: Counter[str],
) -> None:
    writers["unified"].write(json.dumps(record, ensure_ascii=False) + "\n")
    for module in record.get("module_targets", []):
        if module in module_writers:
            module_writers[module].write(json.dumps(record, ensure_ascii=False) + "\n")
            module_counts[module] += 1


def ensure_output_paths(output_dir: Path) -> tuple[Path, Path, Path]:
    unified_dir = output_dir
    modules_dir = output_dir / "by_module"
    manifests_dir = output_dir / "manifests"
    unified_dir.mkdir(parents=True, exist_ok=True)
    modules_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    return unified_dir, modules_dir, manifests_dir


def write_manifest(
    manifests_dir: Path,
    stats: NormalizationStats,
    module_counts: Counter[str],
    args: argparse.Namespace,
) -> None:
    now = datetime.now(UTC).isoformat()
    manifest = {
        "dataset": "NarrativeOS-Normalized-Corpus",
        "version": "1.0.0",
        "generated_at": now,
        "sources": {
            "koconovel_dir": str(Path(args.koconovel_dir)),
            "korean_webnovel_dir": str(Path(args.korean_corpus_dir)),
        },
        "records": {
            "total": stats.records_total,
            "koconovel": stats.koconovel_records,
            "korean_webnovel": stats.korean_webnovel_records,
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
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_readme(output_dir: Path) -> None:
    readme = """# NarrativeOS Normalized Datasets

This directory contains normalized records for NarrativeOS modules.

## Files

- unified.jsonl: unified records from all sources
- by_module/*.jsonl: module-specific projections
- manifests/normalization_manifest.json: normalization stats and schema

## Schema

Each line in JSONL follows:

{
  \"record_id\": \"string\",
  \"source_dataset\": \"KoCoNovel|Korean Web Novel Corpus\",
  \"language\": \"ko|unknown\",
  \"module_targets\": [\"module_name\"],
  \"record_type\": \"scene_fragment|paragraph\",
  \"text\": \"normalized text\",
  \"source\": {...},
  \"annotations\": {...},
  \"features\": {...}
}
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    args = parse_args()
    koconovel_dir = Path(args.koconovel_dir)
    korean_corpus_dir = Path(args.korean_corpus_dir)
    output_dir = Path(args.output_dir)

    unified_dir, modules_dir, manifests_dir = ensure_output_paths(output_dir)

    all_modules = sorted(set(KOCONOVEL_MODULES + KOREAN_WEBNOVEL_MODULES))
    stats = NormalizationStats()
    module_counts: Counter[str] = Counter()

    writers: dict[str, Any] = {
        "unified": (unified_dir / "unified.jsonl").open("w", encoding="utf-8"),
    }
    module_writers: dict[str, Any] = {
        module: (modules_dir / f"{module}.jsonl").open("w", encoding="utf-8")
        for module in all_modules
    }

    try:
        process_koconovel(koconovel_dir, writers, module_writers, stats, module_counts)
        process_korean_webnovel(korean_corpus_dir, writers, module_writers, stats, module_counts)
    finally:
        for handle in list(writers.values()) + list(module_writers.values()):
            handle.close()

    write_manifest(manifests_dir, stats, module_counts, args)
    write_readme(output_dir)

    print(json.dumps({
        "status": "ok",
        "output_dir": str(output_dir),
        "records_total": stats.records_total,
        "koconovel_records": stats.koconovel_records,
        "korean_webnovel_records": stats.korean_webnovel_records,
        "parse_errors": stats.parse_errors,
        "module_record_counts": dict(module_counts),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
