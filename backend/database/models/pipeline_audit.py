from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class PipelineAuditTrail(Base):
    __tablename__ = "pipeline_audit_trails"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    scene_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    scene_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branch: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rejected_before_persist: Mapped[bool] = mapped_column(default=False, nullable=False)
    scene_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gate_json: Mapped[dict[str, object]] = mapped_column("gate", JSON, default=dict)
    reasoning_json: Mapped[dict[str, object]] = mapped_column("reasoning", JSON, default=dict)
    verification_json: Mapped[dict[str, object]] = mapped_column("verification", JSON, default=dict)
    replay_verification_json: Mapped[dict[str, object]] = mapped_column("replay_verification", JSON, default=dict)
    payload_json: Mapped[dict[str, object]] = mapped_column("payload", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())