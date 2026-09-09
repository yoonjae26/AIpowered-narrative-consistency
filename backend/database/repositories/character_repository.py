from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.character import Character


class CharacterRepository:
    def __init__(self, db: Session, commit_on_write: bool = True) -> None:
        self.db = db
        self._commit_on_write = commit_on_write

    def list(self) -> list[Character]:
        stmt = select(Character).order_by(Character.created_at.asc())
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return len(self.list())

    def get(self, character_id: str) -> Character | None:
        return self.db.get(Character, character_id)

    def get_by_name(self, name: str) -> Character | None:
        stmt = select(Character).where(Character.name.ilike(name))
        return self.db.scalars(stmt).first()

    def create(
        self,
        character_id: str,
        name: str,
        role: str,
        traits: list[str],
        goals: list[str],
        background: str | None,
        status: str,
        metadata: dict[str, object],
    ) -> Character:
        character = Character(
            id=character_id,
            name=name,
            role=role,
            traits=traits,
            goals=goals,
            background=background,
            status=status,
            metadata_json=metadata,
        )
        self.db.add(character)
        self.db.flush()
        if self._commit_on_write:
            self.db.commit()
        self.db.refresh(character)
        return character

    def upsert(self, character_id: str, fields: dict[str, object]) -> Character:
        character = self.get(character_id)
        if character is None:
            character = Character(id=character_id, name=str(fields.get("name") or "이름 없는 인물"))
        if "metadata" in fields:
            fields["metadata_json"] = fields.pop("metadata")
        for key, value in fields.items():
            setattr(character, key, value)
        character.updated_at = datetime.now(UTC)
        self.db.add(character)
        self.db.flush()
        if self._commit_on_write:
            self.db.commit()
        self.db.refresh(character)
        return character
