from __future__ import annotations

from typing import Any

from backend.cache.redis_client import RedisClient


class EmbeddingCache:
	def __init__(self, redis_client: RedisClient | None = None) -> None:
		self.redis = redis_client or RedisClient()

	def get(self, cache_key: str) -> list[float] | None:
		value = self.redis.client.get(f"embedding:{cache_key}")
		return value

	def set(self, cache_key: str, embedding: list[float]) -> bool:
		return self.redis.client.set(f"embedding:{cache_key}", embedding)

	def delete(self, cache_key: str) -> int:
		return self.redis.client.delete(f"embedding:{cache_key}")
