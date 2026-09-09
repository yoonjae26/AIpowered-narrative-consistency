from __future__ import annotations

import re

from backend.rag.embeddings.chunk_strategy import ChunkStrategy
from backend.rag.embeddings.embedder import HashEmbedder
from backend.rag.retrieval.semantic_search import SearchHit, SemanticSearch

# Korean particles to strip from query tokens before matching
_KO_PARTICLE_SUFFIX = re.compile(
    r"(을|를|은|는|이|가|의|와|과|에|로|으로|도|만|까지|부터|에서|이야|야|고|며|서|면|랑|이랑)$"
)
_STRIP_PUNCT = re.compile(r"[?!.,;:\"'""''「」『』()\[\]【】]")
_MIN_TOKEN_LEN = 2


def _tokenize_query(text: str) -> list[str]:
    cleaned = _STRIP_PUNCT.sub("", text.lower())
    tokens: list[str] = []
    for tok in cleaned.split():
        stripped = _KO_PARTICLE_SUFFIX.sub("", tok)
        if len(stripped) >= _MIN_TOKEN_LEN:
            tokens.append(stripped)
    return tokens


def _keyword_score(query_tokens: list[str], content: str) -> float:
    if not query_tokens:
        return 0.0
    content_lower = content.lower()
    matched = sum(1 for t in query_tokens if t in content_lower)
    return matched / len(query_tokens)


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
        query_tokens = _tokenize_query(query)
        is_hash_mode = isinstance(self.semantic_search.embedder, HashEmbedder)

        if is_hash_mode:
            # Hash embedder gives meaningless cosine scores (~0.68 for all pairs).
            # Fall back to keyword-only matching so results are actually relevant.
            results: list[SearchHit] = []
            for doc_id, (content, _, metadata) in self.semantic_search._documents.items():
                score = _keyword_score(query_tokens, content)
                if score > 0:
                    results.append(SearchHit(id=doc_id, content=content, score=score, metadata=metadata))
            results.sort(key=lambda h: h.score, reverse=True)
            return results[:limit]

        # Real embeddings: semantic score + small keyword boost for re-ranking
        semantic_hits = self.semantic_search.search(query, limit=max(limit * 3, 15))
        rescored: list[SearchHit] = []
        for hit in semantic_hits:
            kw = _keyword_score(query_tokens, hit.content)
            combined = hit.score + 0.15 * kw
            rescored.append(SearchHit(
                id=hit.id, content=hit.content,
                score=combined, metadata=hit.metadata,
            ))
        rescored.sort(key=lambda h: h.score, reverse=True)
        return rescored[:limit]
