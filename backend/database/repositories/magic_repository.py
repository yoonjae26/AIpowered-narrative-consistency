from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.magic_rule import MagicRule


class MagicRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, name: str, description: str, cost: str | None, limitations: list[str]) -> MagicRule:
        rule = self.db.get(MagicRule, name)
        if rule is None:
            rule = MagicRule(name=name, description=description, cost=cost, limitations=limitations)
        else:
            rule.description = description
            rule.cost = cost
            rule.limitations = limitations
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def list(self) -> list[MagicRule]:
        stmt = select(MagicRule).order_by(MagicRule.name.asc())
        return list(self.db.scalars(stmt).all())
