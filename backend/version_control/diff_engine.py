from __future__ import annotations

import difflib


class DiffEngine:
	def unified_diff(self, before: str, after: str, fromfile: str = "before", tofile: str = "after") -> str:
		return "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile=fromfile, tofile=tofile, lineterm=""))

	def changed_lines(self, before: str, after: str) -> list[str]:
		diff = difflib.ndiff(before.splitlines(), after.splitlines())
		return [line for line in diff if line.startswith(("+ ", "- "))]
