from __future__ import annotations

from backend.core.config import get_settings
from backend.llm.providers.anthropic import AnthropicProvider
from backend.llm.providers.base import BaseLLMProvider
from backend.llm.providers.openai import OpenAIProvider
from backend.llm.providers.qwen import QwenProvider


def create_llm_provider(provider_name: str | None = None) -> BaseLLMProvider:
	settings = get_settings()
	selected = (provider_name or settings.llm_provider or "qwen").lower()

	if selected == "qwen":
		return QwenProvider()
	if selected == "openai":
		return OpenAIProvider()
	if selected == "anthropic":
		return AnthropicProvider()

	raise ValueError(f"Unsupported LLM provider: {selected}")


__all__ = [
	"BaseLLMProvider",
	"OpenAIProvider",
	"AnthropicProvider",
	"QwenProvider",
	"create_llm_provider",
]
