from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models.project import Project


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[Project]:
        stmt = select(Project).order_by(Project.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def get(self, project_id: str) -> Project | None:
        return self.db.get(Project, project_id)

    def get_by_title(self, title: str) -> Project | None:
        stmt = select(Project).where(Project.title == title)
        return self.db.scalar(stmt)

    def create(self, title: str, description: str | None = None, status: str = "draft") -> Project:
        project = Project(title=title, description=description, status=status)
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def update(self, project: Project, **fields: object) -> Project:
        for key, value in fields.items():
            setattr(project, key, value)
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete(self, project: Project) -> None:
        self.db.delete(project)
        self.db.commit()
