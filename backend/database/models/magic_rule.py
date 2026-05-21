from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class MagicRule(Base):
    __tablename__ = "magic_rules"

    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    cost: Mapped[str | None] = mapped_column(String(255), nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
