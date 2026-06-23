from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.database.models.relationship import Relationship


class RelationshipRepository:
    def __init__(self, db: Session, commit_on_write: bool = True) -> None:
        self.db = db
        self._commit_on_write = commit_on_write

    def list(self, character_id: str | None = None) -> list[Relationship]:
        stmt = select(Relationship).order_by(Relationship.created_at.asc())
        if character_id:
            stmt = stmt.where(or_(Relationship.source == character_id, Relationship.target == character_id))
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return len(self.list())

    def get(self, relationship_id: int) -> Relationship | None:
        return self.db.get(Relationship, relationship_id)

    def create(
        self,
        source: str | None = None,
        target: str | None = None,
        relationship_type: str = "related",
        strength: float = 0.5,
        notes: list[str] | None = None,
        relationship_id: str | None = None,
        source_id: str | None = None,
        target_id: str | None = None,
        note: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Relationship:
        del relationship_id, metadata
        src = source_id or source
        tgt = target_id or target
        if not src or not tgt:
            raise ValueError("source/target is required")
        merged_notes = list(notes or [])
        if note:
            merged_notes.append(note)

        relationship = Relationship(
            source=src,
            target=tgt,
            relationship_type=relationship_type,
            strength=strength,
            notes=merged_notes,
        )
        self.db.add(relationship)
        self.db.flush()
        if self._commit_on_write:
            self.db.commit()
        self.db.refresh(relationship)
        return relationship

    def upsert(self, relationship_id: int, fields: dict[str, object]) -> Relationship:
        relationship = self.get(relationship_id)
        if relationship is None:
            raise ValueError(f"relationship not found: {relationship_id}")

        note = fields.pop("note", None)
        if note:
            relationship.notes = list(relationship.notes or []) + [str(note)]

        metadata = fields.pop("metadata", None)
        if isinstance(metadata, dict) and metadata:
            relationship.notes = list(relationship.notes or []) + [f"metadata={metadata}"]

        for key, value in fields.items():
            if hasattr(relationship, key):
                setattr(relationship, key, value)
        relationship.created_at = relationship.created_at or datetime.now(UTC)
        self.db.add(relationship)
        self.db.flush()
        if self._commit_on_write:
            self.db.commit()
        self.db.refresh(relationship)
        return relationship
