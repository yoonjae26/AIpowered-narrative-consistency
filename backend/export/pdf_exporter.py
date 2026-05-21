from __future__ import annotations

from io import BytesIO

try:
	from reportlab.lib.pagesizes import A4
	from reportlab.pdfgen import canvas
except Exception:  # pragma: no cover - optional dependency fallback
	A4 = None
	canvas = None


class PDFExporter:
	def export(self, title: str, content: str) -> bytes:
		if canvas is None:
			return f"{title}\n\n{content}\n".encode("utf-8")
		buffer = BytesIO()
		pdf = canvas.Canvas(buffer, pagesize=A4)
		pdf.setTitle(title)
		pdf.drawString(40, 800, title)
		y = 780
		for line in content.splitlines():
			pdf.drawString(40, y, line)
			y -= 16
		pdf.save()
		return buffer.getvalue()
