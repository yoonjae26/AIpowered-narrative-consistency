from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.timeline_event import TimelineEvent


class TimelineRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[TimelineEvent]:
        stmt = select(TimelineEvent).order_by(TimelineEvent.happened_at.asc())
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return len(self.list())

    def create(self, title: str, description: str | None, happened_at: datetime, metadata: dict[str, object] | None = None) -> TimelineEvent:
        event = TimelineEvent(title=title, description=description, happened_at=happened_at, metadata_json=metadata or {})
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event
