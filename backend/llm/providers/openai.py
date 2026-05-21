from __future__ import annotations

from typing import Any

from backend.core.config import get_settings
from backend.llm.providers.base import BaseLLMProvider, LLMMessage, LLMResponse

try:
	from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency fallback
	OpenAI = None


class OpenAIProvider(BaseLLMProvider):
	name = "openai"

	def __init__(self, model: str = "gpt-4o-mini") -> None:
		self.model = model
		settings = get_settings()
		self._client = OpenAI(api_key=settings.openai_api_key) if OpenAI and settings.openai_api_key else None

	def complete(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
		if self._client is None:
			return LLMResponse(content="\n".join(message.content for message in messages), metadata={"provider": self.name, "fallback": True})
		response = self._client.chat.completions.create(model=self.model, messages=[message.__dict__ for message in messages], **kwargs)
		content = response.choices[0].message.content or ""
		return LLMResponse(content=content, metadata={"provider": self.name, "model": self.model})
