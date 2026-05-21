from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.core.constants import DEFAULT_PROJECT_TITLE, ProjectStatus
from backend.core.exceptions import ConflictError, NotFoundError
from backend.database.repositories.project_repository import ProjectRepository


router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
	title: str = Field(default=DEFAULT_PROJECT_TITLE, min_length=1, max_length=200)
	description: str | None = None


class ProjectUpdate(BaseModel):
	title: str | None = None
	description: str | None = None
	status: ProjectStatus | None = None


class ProjectRecord(BaseModel):
	id: str
	title: str
	description: str | None = None
	status: ProjectStatus = ProjectStatus.DRAFT
	created_at: datetime
	updated_at: datetime


@router.get("", response_model=list[ProjectRecord])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRecord]:
	repo = ProjectRepository(db)
	return [
		ProjectRecord(
			id=project.id,
			title=project.title,
			description=project.description,
			status=ProjectStatus(project.status),
			created_at=project.created_at,
			updated_at=project.updated_at,
		)
		for project in repo.list()
	]


@router.post("", response_model=ProjectRecord, status_code=status.HTTP_201_CREATED)
def create_project(request: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRecord:
	repo = ProjectRepository(db)
	if repo.get_by_title(request.title) is not None:
		raise ConflictError(message="Project title already exists", title=request.title)

	project = repo.create(title=request.title, description=request.description, status=ProjectStatus.DRAFT.value)
	return ProjectRecord(
		id=project.id,
		title=project.title,
		description=project.description,
		status=ProjectStatus(project.status),
		created_at=project.created_at,
		updated_at=project.updated_at,
	)


@router.get("/{project_id}", response_model=ProjectRecord)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectRecord:
	repo = ProjectRepository(db)
	project = repo.get(project_id)
	if project is None:
		raise NotFoundError(message="Project not found", project_id=project_id)
	return ProjectRecord(
		id=project.id,
		title=project.title,
		description=project.description,
		status=ProjectStatus(project.status),
		created_at=project.created_at,
		updated_at=project.updated_at,
	)


@router.patch("/{project_id}", response_model=ProjectRecord)
def update_project(project_id: str, request: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectRecord:
	repo = ProjectRepository(db)
	project = repo.get(project_id)
	if project is None:
		raise NotFoundError(message="Project not found", project_id=project_id)

	patch = request.model_dump(exclude_unset=True)
	if "status" in patch and isinstance(patch["status"], ProjectStatus):
		patch["status"] = patch["status"].value
	project = repo.update(project, **patch)
	return ProjectRecord(
		id=project.id,
		title=project.title,
		description=project.description,
		status=ProjectStatus(project.status),
		created_at=project.created_at,
		updated_at=project.updated_at,
	)


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = ProjectRepository(db)
	project = repo.get(project_id)
	if project is None:
		raise NotFoundError(message="Project not found", project_id=project_id)
	repo.delete(project)
	return {"status": "deleted", "project_id": project_id}
