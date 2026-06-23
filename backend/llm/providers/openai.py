from __future__ import annotations

from typing import Any

from backend.core.config import get_settings
from backend.llm.providers.base import BaseLLMProvider, LLMMessage, LLMResponse
from backend.observability.langfuse_client import LangfuseClient
from backend.observability.metrics import record_token_usage
from backend.observability.structured_logger import get_logger, log_prompt_event

try:
	from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency fallback
	OpenAI = None


class OpenAIProvider(BaseLLMProvider):
	name = "openai"

	def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
		settings = get_settings()
		self.model = model or settings.llm_model
		resolved_base_url = base_url or settings.llm_base_url
		api_key = settings.openai_api_key or "not-needed-for-local"
		can_initialize_client = OpenAI is not None and (settings.openai_api_key is not None or resolved_base_url is not None)
		self._client = OpenAI(api_key=api_key, base_url=resolved_base_url) if can_initialize_client else None
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
		response = self._client.chat.completions.create(model=self.model, messages=wire_messages, **kwargs)
		content = response.choices[0].message.content or ""
		usage = {
			"prompt_tokens": int(getattr(response.usage, "prompt_tokens", 0) or 0),
			"completion_tokens": int(getattr(response.usage, "completion_tokens", 0) or 0),
			"total_tokens": int(getattr(response.usage, "total_tokens", 0) or 0),
		}
		record_token_usage(self.name, usage)
		metadata = {"provider": self.name, "model": self.model, "usage": usage}
		log_prompt_event(self._logger, self.name, self.model, prompt_text, content, metadata)
		self._langfuse.log_generation(self.name, self.model, prompt_text, content, usage=usage, metadata={"base_url": getattr(self._client, "base_url", None)})
		return LLMResponse(content=content, metadata=metadata)
