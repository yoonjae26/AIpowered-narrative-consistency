from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class IndexedDocument:
	id: str
	content: str
	metadata: dict[str, object] = field(default_factory=dict)


class DocumentIndex:
	def __init__(self) -> None:
		self._documents: dict[str, IndexedDocument] = {}

	def add(self, document_id: str, content: str, **metadata: object) -> IndexedDocument:
		document = IndexedDocument(id=document_id, content=content, metadata=dict(metadata))
		self._documents[document_id] = document
		return document

	def get(self, document_id: str) -> IndexedDocument | None:
		return self._documents.get(document_id)

	def list(self) -> list[IndexedDocument]:
		return list(self._documents.values())
