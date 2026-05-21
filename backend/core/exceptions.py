from dataclasses import dataclass, field

from fastapi import HTTPException, status


@dataclass(slots=True)
class ErrorContext:
	code: str
	message: str
	status_code: int = status.HTTP_400_BAD_REQUEST
	details: dict[str, object] = field(default_factory=dict)


class NarrativeError(Exception):
	def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST, **details: object) -> None:
		super().__init__(message)
		self.code = code
		self.message = message
		self.status_code = status_code
		self.details = details


class AuthenticationError(NarrativeError):
	def __init__(self, message: str = "Authentication failed", **details: object) -> None:
		super().__init__("authentication_error", message, status.HTTP_401_UNAUTHORIZED, **details)


class AuthorizationError(NarrativeError):
	def __init__(self, message: str = "Not permitted", **details: object) -> None:
		super().__init__("authorization_error", message, status.HTTP_403_FORBIDDEN, **details)


class NotFoundError(NarrativeError):
	def __init__(self, message: str = "Resource not found", **details: object) -> None:
		super().__init__("not_found", message, status.HTTP_404_NOT_FOUND, **details)


class ConflictError(NarrativeError):
	def __init__(self, message: str = "Conflict detected", **details: object) -> None:
		super().__init__("conflict", message, status.HTTP_409_CONFLICT, **details)


class ServiceUnavailableError(NarrativeError):
	def __init__(self, message: str = "Service unavailable", **details: object) -> None:
		super().__init__("service_unavailable", message, status.HTTP_503_SERVICE_UNAVAILABLE, **details)


def to_http_exception(error: NarrativeError) -> HTTPException:
	return HTTPException(status_code=error.status_code, detail={"code": error.code, "message": error.message, "details": error.details})
