from __future__ import annotations

from backend.consistency.checkers.character_checker import CharacterChecker


class CharacterAgent:
	def __init__(self, checker: CharacterChecker | None = None) -> None:
		self.checker = checker or CharacterChecker()

	def analyze(self, text: str, names: list[str]) -> list[str]:
		return [issue.message for issue in self.checker.check_names(text, names)]
