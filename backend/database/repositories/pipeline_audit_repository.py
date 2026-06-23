from __future__ import annotations

from sqlalchemy.orm import Session

from backend.database.models.pipeline_audit import PipelineAuditTrail


class PipelineAuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: dict[str, object]) -> PipelineAuditTrail:
        record = PipelineAuditTrail(
            scene_id=payload.get("scene_id") if isinstance(payload.get("scene_id"), str) else None,
            scene_title=payload.get("scene_title") if isinstance(payload.get("scene_title"), str) else None,
            branch=str(payload.get("branch") or "main"),
            decision=str(payload.get("decision") or "reject"),
            rejected_before_persist=bool(payload.get("rejected_before_persist", False)),
            scene_hash=str(payload.get("scene_hash") or "") or None,
            gate_json=dict(payload.get("gate") or {}),
            reasoning_json=dict(payload.get("reasoning") or {}),
            verification_json=dict(payload.get("verification") or {}),
            replay_verification_json=dict(payload.get("replay_verification") or {}),
            payload_json=dict(payload),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record