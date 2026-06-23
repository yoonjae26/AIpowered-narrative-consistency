from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db, get_token_payload
from backend.core.constants import DEFAULT_PROJECT_TITLE, ProjectStatus
from backend.core.exceptions import ConflictError, NotFoundError
from backend.database.models.project import Project
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


def _to_record(project: Project) -> ProjectRecord:
	return ProjectRecord(
		id=project.id,
		title=project.title,
		description=project.description,
		status=ProjectStatus(project.status),
		created_at=project.created_at,
		updated_at=project.updated_at,
	)


def _owner_id(payload: dict[str, object]) -> str:
	return str(payload["sub"])


@router.get("", response_model=list[ProjectRecord])
def list_projects(
	payload: dict[str, object] = Depends(get_token_payload),
	db: Session = Depends(get_db),
) -> list[ProjectRecord]:
	repo = ProjectRepository(db)
	return [_to_record(p) for p in repo.list(owner_id=_owner_id(payload))]


@router.post("", response_model=ProjectRecord, status_code=status.HTTP_201_CREATED)
def create_project(
	request: ProjectCreate,
	payload: dict[str, object] = Depends(get_token_payload),
	db: Session = Depends(get_db),
) -> ProjectRecord:
	repo = ProjectRepository(db)
	if repo.get_by_title(request.title) is not None:
		raise ConflictError(message="Project title already exists", title=request.title)
	project = repo.create(
		title=request.title,
		owner_id=_owner_id(payload),
		description=request.description,
		status=ProjectStatus.DRAFT.value,
	)
	return _to_record(project)


@router.get("/{project_id}", response_model=ProjectRecord)
def get_project(
	project_id: str,
	payload: dict[str, object] = Depends(get_token_payload),
	db: Session = Depends(get_db),
) -> ProjectRecord:
	repo = ProjectRepository(db)
	project = repo.get(project_id)
	if project is None or project.owner_id != _owner_id(payload):
		raise NotFoundError(message="Project not found", project_id=project_id)
	return _to_record(project)


@router.patch("/{project_id}", response_model=ProjectRecord)
def update_project(
	project_id: str,
	request: ProjectUpdate,
	payload: dict[str, object] = Depends(get_token_payload),
	db: Session = Depends(get_db),
) -> ProjectRecord:
	repo = ProjectRepository(db)
	project = repo.get(project_id)
	if project is None or project.owner_id != _owner_id(payload):
		raise NotFoundError(message="Project not found", project_id=project_id)
	patch = request.model_dump(exclude_unset=True)
	if "status" in patch and isinstance(patch["status"], ProjectStatus):
		patch["status"] = patch["status"].value
	project = repo.update(project, **patch)
	return _to_record(project)


@router.delete("/{project_id}")
def delete_project(
	project_id: str,
	payload: dict[str, object] = Depends(get_token_payload),
	db: Session = Depends(get_db),
) -> dict[str, object]:
	repo = ProjectRepository(db)
	project = repo.get(project_id)
	if project is None or project.owner_id != _owner_id(payload):
		raise NotFoundError(message="Project not found", project_id=project_id)
	repo.delete(project)
	return {"status": "deleted", "project_id": project_id}
