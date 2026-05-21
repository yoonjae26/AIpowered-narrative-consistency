from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth.jwt_handler import validate_token
from backend.auth.session_manager import SessionManager, session_manager
from backend.core.config import Settings, get_settings
from backend.database.session import get_db_session


def get_app_settings() -> Settings:
	return get_settings()


def get_session_manager() -> SessionManager:
	return session_manager


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
	if not authorization:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
	scheme, _, token = authorization.partition(" ")
	if scheme.lower() != "bearer" or not token:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
	return token


def get_token_payload(token: str = Depends(get_bearer_token)) -> dict[str, object]:
	try:
		return validate_token(token, expected_type="access")
	except ValueError as exc:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def get_db() -> Session:
	yield from get_db_session()
