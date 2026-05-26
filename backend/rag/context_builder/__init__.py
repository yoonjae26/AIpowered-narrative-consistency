from __future__ import annotations

from backend.rag.context_builder.narrative_memory import NarrativeMemoryHit, NarrativeMemoryService


def build_context(snippets: list[str], max_length: int = 4000) -> str:
	context = "\n\n".join(snippet.strip() for snippet in snippets if snippet.strip())
	return context[:max_length]


__all__ = ["NarrativeMemoryHit", "NarrativeMemoryService", "build_context"]
