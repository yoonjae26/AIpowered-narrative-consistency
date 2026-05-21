from __future__ import annotations


def generate_warnings(issues: list[object]) -> list[str]:
	warnings: list[str] = []
	for issue in issues:
		message = getattr(issue, "message", str(issue))
		warnings.append(message)
	return warnings
