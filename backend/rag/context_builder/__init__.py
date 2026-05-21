from __future__ import annotations


def build_context(snippets: list[str], max_length: int = 4000) -> str:
	context = "\n\n".join(snippet.strip() for snippet in snippets if snippet.strip())
	return context[:max_length]
