from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.database.models.lore_fact import LoreFact


class LoreRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[LoreFact]:
        stmt = select(LoreFact).order_by(LoreFact.key.asc())
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return len(self.list())

    def get(self, key: str) -> LoreFact | None:
        return self.db.get(LoreFact, key)

    def upsert(self, key: str, value: str, source: str | None, tags: list[str]) -> LoreFact:
        fact = self.get(key)
        if fact is None:
            fact = LoreFact(key=key, value=value, source=source, tags=tags)
        else:
            fact.value = value
            fact.source = source
            fact.tags = tags
        self.db.add(fact)
        self.db.commit()
        self.db.refresh(fact)
        return fact

    def search(self, query: str) -> list[LoreFact]:
        like = f"%{query}%"
        stmt = select(LoreFact).where(or_(LoreFact.key.ilike(like), LoreFact.value.ilike(like)))
        return list(self.db.scalars(stmt).all())
