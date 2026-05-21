from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.canon_entry import CanonEntry


class CanonRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, key: str) -> CanonEntry | None:
        return self.db.get(CanonEntry, key)

    def upsert(self, key: str, value: str, immutable: bool, aliases: list[str]) -> CanonEntry:
        entry = self.get(key)
        if entry is None:
            entry = CanonEntry(key=key, value=value, immutable=immutable, aliases=aliases)
        else:
            entry.value = value
            entry.immutable = immutable
            entry.aliases = aliases
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list(self) -> list[CanonEntry]:
        stmt = select(CanonEntry).order_by(CanonEntry.key.asc())
        return list(self.db.scalars(stmt).all())
