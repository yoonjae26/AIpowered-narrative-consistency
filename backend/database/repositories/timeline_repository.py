from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.timeline_event import TimelineEvent


class TimelineRepository:
    def __init__(self, db: Session, commit_on_write: bool = True) -> None:
        self.db = db
        self._commit_on_write = commit_on_write

    def list(self) -> list[TimelineEvent]:
        stmt = select(TimelineEvent).order_by(TimelineEvent.happened_at.asc())
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return len(self.list())

    def create(
        self,
        event_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        event_type: str | None = None,
        characters: list[str] | None = None,
        timestamp: datetime | None = None,
        metadata: dict[str, object] | None = None,
        happened_at: datetime | None = None,
    ) -> TimelineEvent:
        payload = dict(metadata or {})
        if event_type is not None:
            payload.setdefault("event_type", event_type)
        if characters is not None:
            payload.setdefault("characters", list(characters))

        event = TimelineEvent(
            id=event_id or uuid4().hex,
            title=title or event_type or "timeline",
            description=description,
            happened_at=timestamp or happened_at or datetime.now(UTC),
            metadata_json=payload,
        )
        self.db.add(event)
        self.db.flush()
        if self._commit_on_write:
            self.db.commit()
        self.db.refresh(event)
        return event
