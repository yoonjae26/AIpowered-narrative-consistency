from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class CanonEntry(Base):
    __tablename__ = "canon_entries"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    immutable: Mapped[bool] = mapped_column(default=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
