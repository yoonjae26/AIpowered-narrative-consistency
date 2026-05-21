from __future__ import annotations

from io import BytesIO

try:
	from ebooklib import epub
except Exception:  # pragma: no cover - optional dependency fallback
	epub = None


class EpubExporter:
	def export(self, title: str, content: str) -> bytes:
		if epub is None:
			return f"{title}\n\n{content}\n".encode("utf-8")
		book = epub.EpubBook()
		book.set_identifier(title.lower().replace(" ", "-"))
		book.set_title(title)
		book.set_language("en")
		chapter = epub.EpubHtml(title=title, file_name="chapter1.xhtml", content=f"<h1>{title}</h1><p>{content}</p>")
		book.add_item(chapter)
		book.toc = (chapter,)
		book.spine = ["nav", chapter]
		epub_bytes = BytesIO()
		epub.write_epub(epub_bytes, book)
		return epub_bytes.getvalue()
