from __future__ import annotations

from dataclasses import dataclass

from backend.llm.providers.base import BaseLLMProvider, LLMMessage


@dataclass(slots=True)
class LoreInsight:
	summary: str


class LoreAgent:
	def __init__(self, provider: BaseLLMProvider) -> None:
		self.provider = provider

	def summarize(self, lore_notes: list[str]) -> LoreInsight:
		prompt = [LLMMessage(role="system", content="You summarize lore notes into actionable canon."), LLMMessage(role="user", content="\n".join(lore_notes))]
		response = self.provider.complete(prompt)
		return LoreInsight(summary=response.content)
