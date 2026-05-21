from __future__ import annotations


class ConflictResolver:
	def resolve(self, issues: list[object]) -> dict[str, object]:
		messages = [getattr(issue, "message", str(issue)) for issue in issues]
		return {"resolved": not bool(issues), "issues": messages, "recommendation": "Review the flagged sections and align them with canon."}
