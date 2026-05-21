from __future__ import annotations

from dataclasses import dataclass

from backend.llm.providers.base import BaseLLMProvider, LLMMessage


@dataclass(slots=True)
class ConsistencyAdvice:
	findings: list[str]


class ConsistencyAgent:
	def __init__(self, provider: BaseLLMProvider) -> None:
		self.provider = provider

	def analyze(self, text: str, reference_notes: list[str] | None = None) -> ConsistencyAdvice:
		prompt = [LLMMessage(role="system", content="You identify narrative consistency issues."), LLMMessage(role="user", content=f"Text: {text}\nReferences: {reference_notes or []}")]
		response = self.provider.complete(prompt)
		findings = [line for line in response.content.splitlines() if line.strip()]
		return ConsistencyAdvice(findings=findings)
