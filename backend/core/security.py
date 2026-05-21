from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from backend.core.config import get_settings

try:
	from passlib.context import CryptContext
except Exception:  # pragma: no cover - optional dependency fallback
	CryptContext = None


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext else None
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
	if _pwd_context is None:
		raise RuntimeError("passlib is not available")
	return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
	if _pwd_context is None:
		return plain_password == hashed_password
	return _pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: str, token_type: str, expires_delta: timedelta, scopes: list[str] | None = None) -> str:
	settings = get_settings()
	now = datetime.now(UTC)
	payload: dict[str, Any] = {
		"sub": subject,
		"type": token_type,
		"iat": int(now.timestamp()),
		"exp": int((now + expires_delta).timestamp()),
		"scopes": scopes or [],
	}
	return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def create_access_token(subject: str, expires_minutes: int | None = None, scopes: list[str] | None = None) -> str:
	settings = get_settings()
	minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
	return _create_token(subject, "access", timedelta(minutes=minutes), scopes=scopes)


def create_refresh_token(subject: str, expires_days: int | None = None) -> str:
	settings = get_settings()
	days = expires_days if expires_days is not None else settings.refresh_token_expire_days
	return _create_token(subject, "refresh", timedelta(days=days))


def decode_token(token: str) -> dict[str, Any]:
	settings = get_settings()
	try:
		payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
	except JWTError as exc:
		raise ValueError("Invalid token") from exc
	if not isinstance(payload, dict):
		raise ValueError("Invalid token payload")
	return payload
