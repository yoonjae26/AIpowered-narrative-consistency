from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.narrative.relationships.relationship_types import RelationshipType
from backend.database.session import Base


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        CheckConstraint("strength >= 0.0 AND strength <= 1.0", name="ck_relationships_strength"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), ForeignKey("characters.id", ondelete="CASCADE"), index=True, nullable=False)
    target: Mapped[str] = mapped_column(String(64), ForeignKey("characters.id", ondelete="CASCADE"), index=True, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), default=RelationshipType.ALLY.value, nullable=False)
    strength: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
