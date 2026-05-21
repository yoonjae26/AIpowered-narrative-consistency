from __future__ import annotations

from dataclasses import dataclass, field

from backend.llm.providers.base import BaseLLMProvider, LLMMessage


@dataclass(slots=True)
class PromptChain:
	provider: BaseLLMProvider
	system_prompt: str
	metadata: dict[str, object] = field(default_factory=dict)

	def run(self, user_prompt: str) -> str:
		messages = [LLMMessage(role="system", content=self.system_prompt), LLMMessage(role="user", content=user_prompt)]
		response = self.provider.complete(messages)
		return response.content
