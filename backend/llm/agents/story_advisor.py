from __future__ import annotations

from dataclasses import dataclass

from backend.llm.providers.base import BaseLLMProvider, LLMMessage


@dataclass(slots=True)
class StoryAdvice:
	recommendation: str
	rationale: str


class StoryAdvisor:
	def __init__(self, provider: BaseLLMProvider) -> None:
		self.provider = provider

	def advise(self, premise: str, constraints: list[str] | None = None) -> StoryAdvice:
		prompt = [LLMMessage(role="system", content="You are a narrative story advisor."), LLMMessage(role="user", content=f"Premise: {premise}\nConstraints: {constraints or []}")]
		response = self.provider.complete(prompt)
		return StoryAdvice(recommendation=response.content, rationale="Generated from the configured LLM provider or fallback.")
