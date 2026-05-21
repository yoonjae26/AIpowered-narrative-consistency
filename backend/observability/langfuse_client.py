from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import get_settings

try:
	from langfuse import Langfuse
except Exception:  # pragma: no cover - optional dependency fallback
	Langfuse = None


@dataclass(slots=True)
class NullLangfuseClient:
	def trace(self, *args, **kwargs):
		return None

	def observe(self, *args, **kwargs):
		return None


class LangfuseClient:
	def __init__(self) -> None:
		settings = get_settings()
		if Langfuse is None or not settings.langfuse_public_key or not settings.langfuse_secret_key:
			self._client = NullLangfuseClient()
		else:
			self._client = Langfuse(public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key)

	@property
	def client(self):
		return self._client
