from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.core.config import get_settings

try:
	import redis
except Exception:  # pragma: no cover - optional dependency fallback
	redis = None


@dataclass(slots=True)
class InMemoryRedis:
	data: dict[str, Any] = field(default_factory=dict)

	def get(self, key: str) -> Any:
		return self.data.get(key)

	def set(self, key: str, value: Any) -> bool:
		self.data[key] = value
		return True

	def delete(self, key: str) -> int:
		return 1 if self.data.pop(key, None) is not None else 0

	def exists(self, key: str) -> bool:
		return key in self.data


class RedisClient:
	def __init__(self, url: str | None = None, decode_responses: bool = True) -> None:
		self.url = url or get_settings().redis_url
		self.decode_responses = decode_responses
		self._client: Any = None
		self._memory = InMemoryRedis()

	def connect(self) -> Any:
		if redis is None:
			self._client = self._memory
			return self._client
		self._client = redis.Redis.from_url(self.url, decode_responses=self.decode_responses)
		return self._client

	@property
	def client(self) -> Any:
		if self._client is None:
			return self.connect()
		return self._client
