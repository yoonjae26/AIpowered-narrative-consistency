from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LogicIssue:
	code: str
	message: str


class LogicChecker:
	def check(self, text: str) -> list[LogicIssue]:
		issues: list[LogicIssue] = []
		lowered = text.lower()
		if "because" in lowered and "however" in lowered:
			issues.append(LogicIssue(code="ambiguous_causality", message="Text mixes causal and adversative cues."))
		return issues
