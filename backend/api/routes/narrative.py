from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.relationship_repository import RelationshipRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.database.repositories.timeline_repository import TimelineRepository
from backend.narrative.character.models import CharacterState, CharacterUpdate
from backend.narrative.relationships.relationship_types import RelationshipType


router = APIRouter(prefix="/narrative", tags=["narrative"])


class LoreFactCreate(BaseModel):
	key: str
	value: str
	source: str | None = None
	tags: set[str] = Field(default_factory=set)


class TimelineEventCreate(BaseModel):
	title: str
	description: str | None = None
	happened_at: datetime | None = None


class SceneCreate(BaseModel):
	title: str
	summary: str | None = None
	beats: list[str] = Field(default_factory=list)
	characters: list[str] = Field(default_factory=list)


class RelationshipCreate(BaseModel):
	...existing code...

# --- State Mutation Engine Integration ---
from backend.narrative.state_engine import NarrativeStateMutationEngine
from fastapi import Body

class SceneInput(BaseModel):
	scene_text: str
	context: dict = Field(default_factory=dict)

# Dependency to provide the state engine with repositories
def get_state_engine(db: Session = Depends(get_db)):
	repositories = {
		"character": CharacterRepository(db),
		"lore": LoreRepository(db),
		"relationship": RelationshipRepository(db),
		"scene": SceneRepository(db),
		"timeline": TimelineRepository(db),
	}
	return NarrativeStateMutationEngine(repositories)

@router.post("/state-mutation", summary="Process scene input and mutate narrative state")
def process_scene_input(
	input: SceneInput = Body(...),
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
):
	"""
	Accepts raw scene text, runs the state mutation pipeline, and returns the result.
	"""
	result = state_engine.process_scene(input.scene_text, input.context)
	return result
	source: str
	target: str
	relationship_type: RelationshipType
	strength: float = 0.5
	note: str | None = None


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, object]:
	characters = CharacterRepository(db)
	scenes = SceneRepository(db)
	timeline = TimelineRepository(db)
	lore = LoreRepository(db)
	relationships = RelationshipRepository(db)
	return {
		"characters": characters.count(),
		"scenes": scenes.count(),
		"timeline_events": timeline.count(),
		"lore_facts": lore.count(),
		"relationships": relationships.count(),
	}


@router.post("/characters", response_model=CharacterState, status_code=status.HTTP_201_CREATED)
def create_character(request: CharacterState, db: Session = Depends(get_db)) -> CharacterState:
	repo = CharacterRepository(db)
	character = repo.create(
		character_id=request.id,
		name=request.name,
		role=request.role.value,
		traits=request.traits,
		goals=request.goals,
		background=request.background,
		status=request.status,
		metadata=request.metadata,
	)
	return CharacterState(
		id=character.id,
		name=character.name,
		role=character.role,
		traits=character.traits,
		goals=character.goals,
		background=character.background,
		status=character.status,
		metadata=character.metadata_json,
		created_at=character.created_at,
		updated_at=character.updated_at,
	)


@router.patch("/characters/{character_id}", response_model=CharacterState)
def update_character(character_id: str, request: CharacterUpdate, db: Session = Depends(get_db)) -> CharacterState:
	repo = CharacterRepository(db)
	patch = request.model_dump(exclude_unset=True)
	if "role" in patch and patch["role"] is not None:
		patch["role"] = patch["role"].value
	character = repo.upsert(character_id, patch)
	return CharacterState(
		id=character.id,
		name=character.name,
		role=character.role,
		traits=character.traits,
		goals=character.goals,
		background=character.background,
		status=character.status,
		metadata=character.metadata_json,
		created_at=character.created_at,
		updated_at=character.updated_at,
	)


@router.get("/characters", response_model=list[CharacterState])
def list_characters(db: Session = Depends(get_db)) -> list[CharacterState]:
	repo = CharacterRepository(db)
	return [
		CharacterState(
			id=item.id,
			name=item.name,
			role=item.role,
			traits=item.traits,
			goals=item.goals,
			background=item.background,
			status=item.status,
			metadata=item.metadata_json,
			created_at=item.created_at,
			updated_at=item.updated_at,
		)
		for item in repo.list()
	]


@router.post("/scenes", response_model=dict[str, object], status_code=status.HTTP_201_CREATED)
def create_scene(request: SceneCreate, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = SceneRepository(db)
	scene = repo.create(title=request.title, summary=request.summary, beats=request.beats, characters=request.characters)
	return {
		"id": scene.id,
		"title": scene.title,
		"summary": scene.summary,
		"beats": scene.beats,
		"characters": scene.characters,
		"created_at": scene.created_at,
	}


@router.get("/scenes")
def list_scenes(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	repo = SceneRepository(db)
	return [
		{
			"id": scene.id,
			"title": scene.title,
			"summary": scene.summary,
			"beats": scene.beats,
			"characters": scene.characters,
			"created_at": scene.created_at,
		}
		for scene in repo.list()
	]


@router.post("/world/lore")
def add_lore_fact(request: LoreFactCreate, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = LoreRepository(db)
	fact = repo.upsert(request.key, request.value, source=request.source, tags=sorted(request.tags))
	return {"key": fact.key, "value": fact.value, "source": fact.source, "tags": fact.tags}


@router.get("/world/lore")
def list_lore_facts(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	repo = LoreRepository(db)
	return [{"key": fact.key, "value": fact.value, "source": fact.source, "tags": fact.tags} for fact in repo.list()]


@router.post("/timeline/events")
def add_timeline_event(request: TimelineEventCreate, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = TimelineRepository(db)
	event = repo.create(title=request.title, description=request.description, happened_at=request.happened_at or datetime.utcnow())
	return {
		"id": event.id,
		"title": event.title,
		"description": event.description,
		"happened_at": event.happened_at,
		"metadata": event.metadata_json,
	}


@router.get("/timeline/events")
def list_timeline_events(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	repo = TimelineRepository(db)
	return [
		{
			"id": event.id,
			"title": event.title,
			"description": event.description,
			"happened_at": event.happened_at,
			"metadata": event.metadata_json,
		}
		for event in repo.list()
	]


@router.post("/relationships")
def add_relationship(request: RelationshipCreate, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = RelationshipRepository(db)
	relationship = repo.create(
		source=request.source,
		target=request.target,
		relationship_type=request.relationship_type.value,
		strength=request.strength,
		notes=[request.note] if request.note else [],
	)
	return {
		"id": relationship.id,
		"source": relationship.source,
		"target": relationship.target,
		"relationship_type": relationship.relationship_type,
		"strength": relationship.strength,
		"notes": relationship.notes,
		"created_at": relationship.created_at,
	}
