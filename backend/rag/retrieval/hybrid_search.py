from __future__ import annotations

from backend.rag.embeddings.chunk_strategy import ChunkStrategy
from backend.rag.retrieval.semantic_search import SearchHit, SemanticSearch


class HybridSearch:
	def __init__(self, semantic_search: SemanticSearch | None = None, chunk_strategy: ChunkStrategy | None = None) -> None:
		self.semantic_search = semantic_search or SemanticSearch()
		self.chunk_strategy = chunk_strategy or ChunkStrategy()

	def index(self, document_id: str, content: str, **metadata: object) -> None:
		chunks = self.chunk_strategy.chunk(content)
		if not chunks:
			self.semantic_search.index(document_id, content, **metadata)
			return
		for index, chunk in enumerate(chunks):
			self.semantic_search.index(f"{document_id}:{index}", chunk, **metadata)

	def search(self, query: str, limit: int = 5) -> list[SearchHit]:
		semantic_hits = self.semantic_search.search(query, limit=limit)
		keyword_hits = [hit for hit in semantic_hits if query.lower() in hit.content.lower()]
		combined = keyword_hits + [hit for hit in semantic_hits if hit not in keyword_hits]
		return combined[:limit]
