from __future__ import annotations

from typing import Any

from backend.core.config import get_settings
from backend.llm.providers.base import BaseLLMProvider, LLMMessage, LLMResponse

try:
	import anthropic
except Exception:  # pragma: no cover - optional dependency fallback
	anthropic = None


class AnthropicProvider(BaseLLMProvider):
	name = "anthropic"

	def __init__(self, model: str = "claude-3-5-sonnet-latest") -> None:
		self.model = model
		settings = get_settings()
		self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if anthropic and settings.anthropic_api_key else None

	def complete(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
		if self._client is None:
			return LLMResponse(content="\n".join(message.content for message in messages), metadata={"provider": self.name, "fallback": True})
		response = self._client.messages.create(model=self.model, max_tokens=kwargs.pop("max_tokens", 1024), messages=[message.__dict__ for message in messages], **kwargs)
		return LLMResponse(content="".join(block.text for block in response.content if hasattr(block, "text")), metadata={"provider": self.name, "model": self.model})
