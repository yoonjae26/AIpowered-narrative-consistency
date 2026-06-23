from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

try:
    import chromadb
except Exception:
    chromadb = None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sqrt(sum(v * v for v in left))
    right_norm = sqrt(sum(v * v for v in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


@dataclass(slots=True)
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, record_id: str, vector: list[float], **payload: Any) -> VectorRecord:
        record = VectorRecord(id=record_id, vector=vector, payload=dict(payload))
        self._records[record_id] = record
        return record

    def get(self, record_id: str) -> VectorRecord | None:
        return self._records.get(record_id)

    def query(self, vector: list[float], limit: int = 5) -> list[VectorRecord]:
        ranked = sorted(
            self._records.values(),
            key=lambda r: _cosine_similarity(vector, r.vector),
            reverse=True,
        )
        return ranked[:limit]

    def reset(self) -> None:
        self._records.clear()

    def size(self) -> int:
        return len(self._records)


# =========================
# GLOBAL SINGLETON (FIX IMPORT ERROR)
# =========================
_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store