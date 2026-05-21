from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.dependencies import get_bearer_token, get_db, get_session_manager, get_token_payload
from backend.auth.jwt_handler import issue_token_pair
from backend.auth.password_utils import check_password, create_password_hash
from backend.auth.session_manager import SessionManager
from backend.core.exceptions import ConflictError, NotFoundError
from backend.database.repositories.user_repository import UserRepository


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
	username: str = Field(min_length=3, max_length=64)
	password: str = Field(min_length=8, max_length=128)
	email: str | None = None
	display_name: str | None = None


class LoginRequest(BaseModel):
	username: str
	password: str


class UserProfile(BaseModel):
	id: str
	username: str
	email: str | None = None
	display_name: str | None = None
	created_at: datetime


class AuthResponse(BaseModel):
	access_token: str
	refresh_token: str
	token_type: str = "bearer"
	user: UserProfile


@router.post("/register", response_model=AuthResponse)
def register(
	request: RegisterRequest,
	session_manager: SessionManager = Depends(get_session_manager),
	db: Session = Depends(get_db),
) -> AuthResponse:
	users = UserRepository(db)
	existing = users.get_by_username(request.username)
	if existing is not None:
		raise ConflictError(message="Username already exists", username=request.username)

	user = users.create(
		username=request.username,
		password_hash=create_password_hash(request.password),
		email=request.email,
		display_name=request.display_name,
	)
	token_pair = issue_token_pair(user.id)
	session_manager.create_session(user_id=user.id, token=token_pair.access_token, username=user.username)
	return AuthResponse(
		access_token=token_pair.access_token,
		refresh_token=token_pair.refresh_token,
		user=UserProfile(
			id=user.id,
			username=user.username,
			email=user.email,
			display_name=user.display_name,
			created_at=user.created_at,
		),
	)


@router.post("/login", response_model=AuthResponse)
def login(
	request: LoginRequest,
	session_manager: SessionManager = Depends(get_session_manager),
	db: Session = Depends(get_db),
) -> AuthResponse:
	users = UserRepository(db)
	user = users.get_by_username(request.username)
	if user is None or not check_password(request.password, user.password_hash):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

	token_pair = issue_token_pair(user.id)
	session_manager.create_session(user_id=user.id, token=token_pair.access_token, username=user.username)
	return AuthResponse(
		access_token=token_pair.access_token,
		refresh_token=token_pair.refresh_token,
		user=UserProfile(
			id=user.id,
			username=user.username,
			email=user.email,
			display_name=user.display_name,
			created_at=user.created_at,
		),
	)


@router.get("/me", response_model=UserProfile)
def me(payload: dict[str, object] = Depends(get_token_payload), db: Session = Depends(get_db)) -> UserProfile:
	user_id = str(payload.get("sub", ""))
	users = UserRepository(db)
	user = users.get_by_id(user_id)
	if user is None:
		raise NotFoundError(message="User not found", user_id=user_id)
	return UserProfile(
		id=user.id,
		username=user.username,
		email=user.email,
		display_name=user.display_name,
		created_at=user.created_at,
	)


@router.post("/logout")
def logout(token: str = Depends(get_bearer_token), session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, object]:
	session_manager.revoke_token(token)
	return {"status": "logged_out"}
