from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from backend.rag.embeddings.embedder import BaseEmbedder, HashEmbedder


def _cosine_similarity(left: list[float], right: list[float]) -> float:
	dot = sum(a * b for a, b in zip(left, right, strict=False))
	left_norm = sqrt(sum(value * value for value in left))
	right_norm = sqrt(sum(value * value for value in right))
	if left_norm == 0 or right_norm == 0:
		return 0.0
	return dot / (left_norm * right_norm)


@dataclass(slots=True)
class SearchHit:
	id: str
	content: str
	score: float
	metadata: dict[str, object] = field(default_factory=dict)


class SemanticSearch:
	def __init__(self, embedder: BaseEmbedder | None = None) -> None:
		self.embedder = embedder or HashEmbedder()
		self._documents: dict[str, tuple[str, list[float], dict[str, object]]] = {}

	def index(self, document_id: str, content: str, **metadata: object) -> None:
		self._documents[document_id] = (content, self.embedder.embed(content), dict(metadata))

	def index_vector(self, document_id: str, content: str, vector: list[float], **metadata: object) -> None:
		self._documents[document_id] = (content, list(vector), dict(metadata))

	def remove(self, document_id: str) -> None:
		self._documents.pop(document_id, None)

	def clear(self) -> None:
		self._documents.clear()

	def dump_documents(self) -> list[dict[str, Any]]:
		return [
			{
				"id": document_id,
				"content": content,
				"vector": list(vector),
				"metadata": dict(metadata),
			}
			for document_id, (content, vector, metadata) in self._documents.items()
		]

	def load_documents(self, documents: list[dict[str, Any]]) -> None:
		self.clear()
		for document in documents:
			self.index_vector(
				document_id=str(document["id"]),
				content=str(document["content"]),
				vector=[float(value) for value in document.get("vector", [])],
				**dict(document.get("metadata", {})),
			)

	def search(self, query: str, limit: int = 5) -> list[SearchHit]:
		query_vector = self.embedder.embed(query)
		ranked: list[SearchHit] = []
		for document_id, (content, vector, metadata) in self._documents.items():
			ranked.append(SearchHit(id=document_id, content=content, score=_cosine_similarity(query_vector, vector), metadata=metadata))
		ranked.sort(key=lambda hit: hit.score, reverse=True)
		return ranked[:limit]
