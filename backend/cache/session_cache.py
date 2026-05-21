from dataclasses import asdict, dataclass
from typing import Any

from backend.cache.redis_client import RedisClient


@dataclass(slots=True)
class SessionPayload:
	session_id: str
	user_id: str
	data: dict[str, Any]


class SessionCache:
	def __init__(self, redis_client: RedisClient | None = None) -> None:
		self.redis = redis_client or RedisClient()

	def set(self, payload: SessionPayload) -> bool:
		return self.redis.client.set(f"session:{payload.session_id}", asdict(payload))

	def get(self, session_id: str) -> dict[str, Any] | None:
		value = self.redis.client.get(f"session:{session_id}")
		return value

	def delete(self, session_id: str) -> int:
		return self.redis.client.delete(f"session:{session_id}")
