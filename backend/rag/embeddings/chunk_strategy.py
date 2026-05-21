from __future__ import annotations


class ChunkStrategy:
	def __init__(self, chunk_size: int = 800, overlap: int = 120) -> None:
		self.chunk_size = chunk_size
		self.overlap = overlap

	def chunk(self, text: str) -> list[str]:
		if not text:
			return []
		chunks: list[str] = []
		start = 0
		text_length = len(text)
		while start < text_length:
			end = min(text_length, start + self.chunk_size)
			chunks.append(text[start:end].strip())
			if end >= text_length:
				break
			start = max(0, end - self.overlap)
		return [chunk for chunk in chunks if chunk]
