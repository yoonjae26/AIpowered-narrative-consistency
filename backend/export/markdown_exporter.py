from __future__ import annotations


class MarkdownExporter:
	def export(self, title: str, content: str) -> str:
		return f"# {title}\n\n{content}\n"
