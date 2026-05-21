from collections import defaultdict, deque
from time import monotonic

from fastapi import Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.core.config import get_settings


class RateLimiterMiddleware(BaseHTTPMiddleware):
	def __init__(self, app) -> None:
		super().__init__(app)
		self._buckets: dict[str, deque[float]] = defaultdict(deque)

	async def dispatch(self, request: Request, call_next):
		settings = get_settings()
		client = request.client.host if request.client else "anonymous"
		now = monotonic()
		bucket = self._buckets[client]
		window = settings.rate_limit_window_seconds
		while bucket and now - bucket[0] > window:
			bucket.popleft()
		if len(bucket) >= settings.rate_limit_requests:
			return Response(content="Rate limit exceeded", status_code=status.HTTP_429_TOO_MANY_REQUESTS)
		bucket.append(now)
		return await call_next(request)
