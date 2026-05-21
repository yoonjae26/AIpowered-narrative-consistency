from __future__ import annotations

from backend.consistency.checkers.logic_checker import LogicChecker


class LogicAgent:
	def __init__(self, checker: LogicChecker | None = None) -> None:
		self.checker = checker or LogicChecker()

	def analyze(self, text: str) -> list[str]:
		return [issue.message for issue in self.checker.check(text)]
