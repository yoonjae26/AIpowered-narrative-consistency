import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


logger = logging.getLogger("narrativeos.api")


class LoggingMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next) -> Response:
		start = time.perf_counter()
		response = await call_next(request)
		duration_ms = (time.perf_counter() - start) * 1000
		logger.info("%s %s -> %s (%.2fms)", request.method, request.url.path, response.status_code, duration_ms)
		response.headers["x-response-time-ms"] = f"{duration_ms:.2f}"
		return response
