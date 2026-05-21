from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

try:
	import chromadb
except Exception:  # pragma: no cover - optional dependency fallback
	chromadb = None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
	dot = sum(a * b for a, b in zip(left, right, strict=False))
	left_norm = sqrt(sum(value * value for value in left))
	right_norm = sqrt(sum(value * value for value in right))
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
		ranked = sorted(self._records.values(), key=lambda record: _cosine_similarity(vector, record.vector), reverse=True)
		return ranked[:limit]
