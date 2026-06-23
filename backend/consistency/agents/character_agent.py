from __future__ import annotations

from typing import Any

from backend.consistency.checkers.character_checker import CharacterChecker
from backend.llm.providers.base import BaseLLMProvider, LLMMessage


class CharacterAgent:
	def __init__(
		self,
		checker: CharacterChecker | None = None,
		llm_provider: BaseLLMProvider | None = None,
	) -> None:
		self.checker = checker or CharacterChecker()
		self._llm = llm_provider

	def analyze(
		self,
		text: str,
		names: list[str],
		character_memories: dict[str, Any] | None = None,
		drift_issues: list[Any] | None = None,
	) -> list[str]:
		findings = [issue.message for issue in self.checker.check_names(text, names)]
		for issue in drift_issues or []:
			findings.append(issue.message)

		for name, memory in (character_memories or {}).items():
			beliefs = {item.lower() for item in getattr(memory, "beliefs", [])}
			if any("trusts" in belief for belief in beliefs) and "betray" in text.lower():
				findings.append(f"{name} carries trust-oriented beliefs, so the betrayal beat may need extra motivation.")

		if self._llm is not None:
			try:
				prompt = "\n".join([
					f"Scene: {text}",
					f"Characters: {', '.join(names) if names else 'none'}",
					f"Drift notes: {[issue.message for issue in (drift_issues or [])]}",
					"Return short bullet findings about personality consistency.",
				])
				response = self._llm.complete([
					LLMMessage(role="system", content="You are a personality-focused narrative analyst."),
					LLMMessage(role="user", content=prompt),
				])
				findings.extend(line.strip("- ") for line in response.content.splitlines() if line.strip())
			except Exception:
				pass

		return list(dict.fromkeys(findings))
