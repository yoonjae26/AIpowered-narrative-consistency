from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return self.db.scalar(stmt)

    def create(self, username: str, password_hash: str, email: str | None = None, display_name: str | None = None) -> User:
        user = User(username=username, password_hash=password_hash, email=email, display_name=display_name)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
