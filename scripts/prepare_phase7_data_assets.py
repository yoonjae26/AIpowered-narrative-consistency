from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.rag.embeddings.embedder import HashEmbedder


SPLITS = ("train", "val", "test")


@dataclass(slots=True)
class SplitStat:
    total: int = 0
    train: int = 0
    val: int = 0
    test: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "train": self.train,
            "val": self.val,
            "test": self.test,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare module splits and NarrativeMemory retrieval index")
    parser.add_argument(
        "--normalized-dir",
        default="datasets/normalized",
        help="Path to normalized dataset directory",
    )
    parser.add_argument(
        "--split-out-dir",
        default="datasets/normalized/splits",
        help="Path to output module split files",
    )
    parser.add_argument(
        "--memory-index-out",
        default=".cache/narrative_memory_index.json",
        help="Path to NarrativeMemory-compatible retrieval index",
    )
    parser.add_argument(
        "--embed-dim",
        type=int,
        default=32,
        help="Embedding dimension for HashEmbedder vectors",
    )
    parser.add_argument(
        "--max-records-for-index",
        type=int,
        default=0,
        help="Optional cap for records in retrieval index (0 = no cap)",
    )
    parser.add_argument(
        "--module-index-dir",
        default=".cache/narrative_memory_modules",
        help="Output directory for module-specific NarrativeMemory indexes",
    )
    parser.add_argument(
        "--max-records-per-module-index",
        type=int,
        default=0,
        help="Optional cap for each module-specific index (0 = no cap)",
    )
    return parser.parse_args()


def split_bucket(record_id: str) -> str:
    value = int(hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if value < 80:
        return "train"
    if value < 90:
        return "val"
    return "test"


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def ensure_split_layout(split_out_dir: Path, module_names: list[str]) -> dict[str, dict[str, Any]]:
    split_out_dir.mkdir(parents=True, exist_ok=True)
    handles: dict[str, dict[str, Any]] = {}
    for module in module_names:
        module_dir = split_out_dir / module
        module_dir.mkdir(parents=True, exist_ok=True)
        handles[module] = {
            split: (module_dir / f"{split}.jsonl").open("w", encoding="utf-8")
            for split in SPLITS
        }
    return handles


def build_module_splits(normalized_dir: Path, split_out_dir: Path) -> dict[str, dict[str, int]]:
    by_module_dir = normalized_dir / "by_module"
    if not by_module_dir.exists():
        raise FileNotFoundError(f"Missing by_module directory: {by_module_dir}")

    module_files = sorted(by_module_dir.glob("*.jsonl"))
    module_names = [path.stem for path in module_files]
    handles = ensure_split_layout(split_out_dir, module_names)
    stats: dict[str, SplitStat] = {name: SplitStat() for name in module_names}

    try:
        for module_file in module_files:
            module = module_file.stem
            for record in iter_jsonl(module_file):
                record_id = str(record.get("record_id") or "")
                if not record_id:
                    continue
                bucket = split_bucket(record_id)
                handles[module][bucket].write(json.dumps(record, ensure_ascii=False) + "\n")
                stat = stats[module]
                stat.total += 1
                if bucket == "train":
                    stat.train += 1
                elif bucket == "val":
                    stat.val += 1
                else:
                    stat.test += 1
    finally:
        for module_handle in handles.values():
            for split_handle in module_handle.values():
                split_handle.close()

    summary = {module: stat.as_dict() for module, stat in stats.items()}
    manifest = {
        "dataset": "NarrativeOS Module Splits",
        "version": "1.0.0",
        "split_policy": "sha256(record_id) -> 80/10/10",
        "modules": summary,
    }
    (split_out_dir / "split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def source_type_for_record(record: dict[str, Any]) -> str:
    record_type = str(record.get("record_type") or "")
    if record_type in {"dialogue_session", "scene_fragment", "conversation"}:
        return "scene"
    if record_type in {"utterance_segment", "event", "dialogue_turn"}:
        return "event"
    if record_type in {"lore_entry", "knowledge_article"}:
        return "lore"
    if record_type in {"entity_profile", "character_profile"}:
        return "character"

    module_targets = [str(item) for item in (record.get("module_targets") or [])]
    if any(item in {"character_cognition", "character_drift"} for item in module_targets):
        return "character"
    if any(item in {"emotion_tracking", "emotional_memory", "emotional_mismatch"} for item in module_targets):
        return "event"
    if any(item in {"entity_linking", "ontology_building", "knowledge_graph", "semantic_retrieval"} for item in module_targets):
        return "lore"
    if any(item in {"lore_management", "canon_reasoning", "timeline_reasoning"} for item in module_targets):
        return "lore"
    if any(item in {"relationship_graph"} for item in module_targets):
        return "character"
    if any(item in {"embeddings", "retrieval_memory", "semantic_indexing", "background_language_understanding"} for item in module_targets):
        return "lore"

    source_dataset = str(record.get("source_dataset") or "")
    if source_dataset == "KoCoNovel":
        return "scene"
    if source_dataset == "Korean Web Novel Corpus":
        return "lore"
    if source_dataset == "AIHub Emotional Dialogue Corpus":
        return "event"
    if source_dataset == "KEMDy20":
        return "event"
    if source_dataset in {"Korean Wikipedia Dataset for GPT2 August 2022", "namuwiki-extracted"}:
        return "lore"
    if source_dataset == "KOREAN-WEBTEXT":
        return "lore"
    return "event"


def _write_index_documents(
    records,
    output_path: Path,
    embedder: HashEmbedder,
    max_records: int,
    index_prefix: str,
) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    by_source_type: dict[str, int] = {"scene": 0, "lore": 0, "character": 0, "event": 0}

    with output_path.open("w", encoding="utf-8") as out:
        out.write('{"documents":[')
        first = True
        for record in records:
            record_id = str(record.get("record_id") or "")
            text = str(record.get("text") or "").strip()
            if not record_id or not text:
                continue

            source_type = source_type_for_record(record)
            metadata = {
                "source_type": source_type,
                "source_dataset": record.get("source_dataset"),
                "record_type": record.get("record_type"),
                "module_targets": record.get("module_targets", []),
                "source": record.get("source", {}),
                "features": record.get("features", {}),
            }
            document = {
                "id": f"{index_prefix}:{record_id}",
                "content": text,
                "vector": embedder.embed(text),
                "metadata": metadata,
            }

            if not first:
                out.write(",")
            out.write(json.dumps(document, ensure_ascii=False))
            first = False

            written += 1
            by_source_type[source_type] = by_source_type.get(source_type, 0) + 1
            if max_records > 0 and written >= max_records:
                break

        out.write("]}")

    return {
        "documents": written,
        "scene": by_source_type.get("scene", 0),
        "lore": by_source_type.get("lore", 0),
        "character": by_source_type.get("character", 0),
        "event": by_source_type.get("event", 0),
    }


def write_memory_index(
    normalized_dir: Path,
    output_path: Path,
    embed_dim: int,
    max_records: int,
) -> dict[str, int]:
    unified_path = normalized_dir / "unified.jsonl"
    if not unified_path.exists():
        raise FileNotFoundError(f"Missing unified file: {unified_path}")

    embedder = HashEmbedder(dimensions=embed_dim)
    return _write_index_documents(
        records=iter_jsonl(unified_path),
        output_path=output_path,
        embedder=embedder,
        max_records=max_records,
        index_prefix="normalized",
    )


def write_module_memory_indexes(
    normalized_dir: Path,
    module_index_dir: Path,
    embed_dim: int,
    max_records_per_module: int,
) -> dict[str, dict[str, int]]:
    by_module_dir = normalized_dir / "by_module"
    if not by_module_dir.exists():
        raise FileNotFoundError(f"Missing by_module directory: {by_module_dir}")

    module_index_dir.mkdir(parents=True, exist_ok=True)
    embedder = HashEmbedder(dimensions=embed_dim)
    summaries: dict[str, dict[str, int]] = {}

    for module_file in sorted(by_module_dir.glob("*.jsonl")):
        module_name = module_file.stem
        out_path = module_index_dir / f"{module_name}.json"
        summaries[module_name] = _write_index_documents(
            records=iter_jsonl(module_file),
            output_path=out_path,
            embedder=embedder,
            max_records=max_records_per_module,
            index_prefix=f"module:{module_name}",
        )

    manifest = {
        "dataset": "NarrativeOS Module Retrieval Indexes",
        "version": "1.0.0",
        "embed_dim": embed_dim,
        "max_records_per_module": max_records_per_module,
        "indexes": summaries,
    }
    (module_index_dir / "index_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summaries


def main() -> None:
    args = parse_args()
    normalized_dir = Path(args.normalized_dir)
    split_out_dir = Path(args.split_out_dir)
    memory_index_out = Path(args.memory_index_out)
    module_index_dir = Path(args.module_index_dir)

    split_summary = build_module_splits(normalized_dir, split_out_dir)
    index_summary = write_memory_index(
        normalized_dir=normalized_dir,
        output_path=memory_index_out,
        embed_dim=args.embed_dim,
        max_records=max(0, int(args.max_records_for_index)),
    )
    module_index_summary = write_module_memory_indexes(
        normalized_dir=normalized_dir,
        module_index_dir=module_index_dir,
        embed_dim=args.embed_dim,
        max_records_per_module=max(0, int(args.max_records_per_module_index)),
    )

    summary = {
        "status": "ok",
        "split_manifest": str(split_out_dir / "split_manifest.json"),
        "module_splits": split_summary,
        "memory_index": {
            "path": str(memory_index_out),
            "summary": index_summary,
            "embed_dim": int(args.embed_dim),
        },
        "module_memory_indexes": {
            "dir": str(module_index_dir),
            "manifest": str(module_index_dir / "index_manifest.json"),
            "summaries": module_index_summary,
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
