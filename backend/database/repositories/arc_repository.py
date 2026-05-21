from __future__ import annotations

from sqlalchemy.orm import Session

from backend.database.models.arc_progress import ArcProgress


class ArcRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, character_id: str) -> ArcProgress | None:
        return self.db.get(ArcProgress, character_id)

    def upsert(self, character_id: str, milestone: str, progress: float, notes: list[str]) -> ArcProgress:
        record = self.get(character_id)
        if record is None:
            record = ArcProgress(character_id=character_id, milestone=milestone, progress=progress, notes=notes)
        else:
            record.milestone = milestone
            record.progress = progress
            record.notes = notes
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record
