from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.database.models.relationship import Relationship


class RelationshipRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, character_id: str | None = None) -> list[Relationship]:
        stmt = select(Relationship).order_by(Relationship.created_at.asc())
        if character_id:
            stmt = stmt.where(or_(Relationship.source == character_id, Relationship.target == character_id))
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return len(self.list())

    def create(self, source: str, target: str, relationship_type: str, strength: float, notes: list[str]) -> Relationship:
        relationship = Relationship(source=source, target=target, relationship_type=relationship_type, strength=strength, notes=notes)
        self.db.add(relationship)
        self.db.commit()
        self.db.refresh(relationship)
        return relationship
