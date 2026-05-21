from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.character import Character


class CharacterRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[Character]:
        stmt = select(Character).order_by(Character.created_at.asc())
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return len(self.list())

    def get(self, character_id: str) -> Character | None:
        return self.db.get(Character, character_id)

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
        self.db.commit()
        self.db.refresh(character)
        return character

    def upsert(self, character_id: str, fields: dict[str, object]) -> Character:
        character = self.get(character_id)
        if character is None:
            character = Character(id=character_id, name=str(fields.get("name") or "Unnamed Character"))
        if "metadata" in fields:
            fields["metadata_json"] = fields.pop("metadata")
        for key, value in fields.items():
            setattr(character, key, value)
        character.updated_at = datetime.utcnow()
        self.db.add(character)
        self.db.commit()
        self.db.refresh(character)
        return character
