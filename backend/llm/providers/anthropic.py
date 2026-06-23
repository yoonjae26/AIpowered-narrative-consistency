from __future__ import annotations

from typing import Any

from backend.core.config import get_settings
from backend.llm.providers.base import BaseLLMProvider, LLMMessage, LLMResponse
from backend.observability.langfuse_client import LangfuseClient
from backend.observability.metrics import record_token_usage
from backend.observability.structured_logger import get_logger, log_prompt_event

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
		self._langfuse = LangfuseClient()
		self._logger = get_logger(__name__)

	def complete(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
		prompt_text = "\n".join(message.content for message in messages)
		wire_messages = [message.as_payload() for message in messages]
		if self._client is None:
			content = prompt_text
			metadata = {"provider": self.name, "model": self.model, "fallback": True, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
			log_prompt_event(self._logger, self.name, self.model, prompt_text, content, metadata)
			self._langfuse.log_generation(self.name, self.model, prompt_text, content, usage=metadata["usage"], metadata={"fallback": True})
			return LLMResponse(content=content, metadata=metadata)
		response = self._client.messages.create(model=self.model, max_tokens=kwargs.pop("max_tokens", 1024), messages=wire_messages, **kwargs)
		content = "".join(block.text for block in response.content if hasattr(block, "text"))
		usage = {
			"prompt_tokens": int(getattr(response.usage, "input_tokens", 0) or 0),
			"completion_tokens": int(getattr(response.usage, "output_tokens", 0) or 0),
			"total_tokens": int((getattr(response.usage, "input_tokens", 0) or 0) + (getattr(response.usage, "output_tokens", 0) or 0)),
		}
		record_token_usage(self.name, usage)
		metadata = {"provider": self.name, "model": self.model, "usage": usage}
		log_prompt_event(self._logger, self.name, self.model, prompt_text, content, metadata)
		self._langfuse.log_generation(self.name, self.model, prompt_text, content, usage=usage, metadata={"max_tokens": kwargs.get("max_tokens", 1024)})
		return LLMResponse(content=content, metadata=metadata)
