from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.security import decode_token


class AuthMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next) -> Response:
		authorization = request.headers.get("authorization")
		request.state.user = None
		if authorization and authorization.lower().startswith("bearer "):
			token = authorization.split(" ", 1)[1].strip()
			try:
				request.state.user = decode_token(token)
			except ValueError:
				request.state.user = None
		return await call_next(request)
