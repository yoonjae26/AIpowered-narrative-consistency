from __future__ import annotations

from backend.core.config import get_settings
from backend.llm.providers.openai import OpenAIProvider


class QwenProvider(OpenAIProvider):
	name = "qwen"

	def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
		settings = get_settings()
		super().__init__(
			model=model or settings.llm_model,
			base_url=base_url or settings.llm_base_url,
		)
