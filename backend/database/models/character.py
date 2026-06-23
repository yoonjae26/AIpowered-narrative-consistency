from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.constants import CharacterRole, DEFAULT_CHARACTER_STATUS
from backend.database.session import Base


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint(
            "role IN ('protagonist', 'antagonist', 'supporting', 'extra')",
            name="ck_characters_role",
        ),
        CheckConstraint(
            "status IN ('active', 'alive', 'dead', 'injured', 'absent', 'unknown')",
            name="ck_characters_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=CharacterRole.SUPPORTING.value, nullable=False)
    traits: Mapped[list[str]] = mapped_column(JSON, default=list)
    goals: Mapped[list[str]] = mapped_column(JSON, default=list)
    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=DEFAULT_CHARACTER_STATUS, nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
