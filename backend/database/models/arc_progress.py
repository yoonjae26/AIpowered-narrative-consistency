from __future__ import annotations

from sqlalchemy import Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class ArcProgress(Base):
    __tablename__ = "arc_progress"

    character_id: Mapped[str] = mapped_column(String(64), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    milestone: Mapped[str] = mapped_column(String(255))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
