from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.scene import Scene


class SceneRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[Scene]:
        stmt = select(Scene).order_by(Scene.created_at.asc())
        return list(self.db.scalars(stmt).all())

    def count(self) -> int:
        return len(self.list())

    def create(self, title: str, summary: str | None, beats: list[str], characters: list[str]) -> Scene:
        scene = Scene(title=title, summary=summary, beats=beats, characters=characters)
        self.db.add(scene)
        self.db.commit()
        self.db.refresh(scene)
        return scene
