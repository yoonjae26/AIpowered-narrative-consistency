from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CharacterIssue:
	character_name: str
	message: str


class CharacterChecker:
	def check_names(self, text: str, names: list[str]) -> list[CharacterIssue]:
		lowered = text.lower()
		issues: list[CharacterIssue] = []
		for name in names:
			if name.lower() not in lowered:
				issues.append(CharacterIssue(character_name=name, message="Character not referenced in text."))
		return issues
