from datetime import datetime

from fastapi import APIRouter, Body, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.database.repositories.canon_repository import CanonRepository
from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.relationship_repository import RelationshipRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.database.repositories.timeline_repository import TimelineRepository
from backend.narrative.character.models import CharacterState, CharacterUpdate
from backend.narrative.relationships.relationship_types import RelationshipType
from backend.narrative.state_engine import NarrativeStateMutationEngine


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
	source: str
	target: str
	relationship_type: RelationshipType
	strength: float = 0.5
	note: str | None = None

class SceneInput(BaseModel):
	scene_text: str
	scene_title: str | None = None
	context: dict = Field(default_factory=dict)


class BranchCreate(BaseModel):
	name: str
	from_branch: str | None = None


class BranchMergeRequest(BaseModel):
	source_branch: str
	target_branch: str | None = None


class CherryPickRequest(BaseModel):
	source_branch: str
	event_ids: list[str] = Field(default_factory=list)
	target_branch: str | None = None


class SnapshotRollbackRequest(BaseModel):
	snapshot_id: str


class QueryRequest(BaseModel):
	query: str


def get_state_engine(db: Session = Depends(get_db)) -> NarrativeStateMutationEngine:
	from backend.llm.providers import create_llm_provider
	try:
		llm_provider = create_llm_provider()
	except Exception:
		llm_provider = None
	repositories = {
		"canon": CanonRepository(db),
		"character": CharacterRepository(db),
		"lore": LoreRepository(db),
		"relationship": RelationshipRepository(db),
		"scene": SceneRepository(db),
		"timeline": TimelineRepository(db),
	}
	return NarrativeStateMutationEngine(repositories, llm_provider=llm_provider)


@router.post("/state-mutation", summary="Process scene input and mutate narrative state")
def process_scene_input(
	input: SceneInput = Body(...),
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
):
	"""
	Accepts raw scene text, runs the full mutation pipeline
	(entity extraction → event generation → state mutation → persistence → consistency check)
	and returns the structured result.
	"""
	ctx = dict(input.context)
	if input.scene_title:
		ctx["scene_title"] = input.scene_title
	return state_engine.process_scene(input.scene_text, ctx)


@router.post("/version-control/branches")
def create_branch(
	request: BranchCreate,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.create_branch(request.name, from_branch=request.from_branch)


@router.get("/version-control/branches")
def list_branches(
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> list[dict[str, object]]:
	return state_engine.list_branches()


@router.post("/version-control/merge")
def merge_branch(
	request: BranchMergeRequest,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object] | None:
	return state_engine.merge_branch(request.source_branch, target_branch=request.target_branch)


@router.post("/version-control/cherry-pick")
def cherry_pick(
	request: CherryPickRequest,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object] | None:
	return state_engine.cherry_pick(request.source_branch, event_ids=request.event_ids, target_branch=request.target_branch)


@router.post("/version-control/checkout/{branch_name}")
def checkout_branch(
	branch_name: str,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object] | None:
	return state_engine.checkout_branch(branch_name)


@router.get("/version-control/snapshots")
def list_snapshots(
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> list[dict[str, object]]:
	return state_engine.list_snapshots()


@router.get("/version-control/diff")
def diff_snapshots(
	snapshot_a: str,
	snapshot_b: str,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, str]:
	return {"diff": state_engine.diff_snapshots(snapshot_a, snapshot_b)}


@router.post("/version-control/rollback")
def rollback_snapshot(
	request: SnapshotRollbackRequest,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object] | None:
	return state_engine.rollback_to_snapshot(request.snapshot_id)


@router.get("/event-sourcing/replay")
def replay_branch(
	branch: str | None = None,
	to_event_id: str | None = None,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.replay_branch(branch=branch, to_event_id=to_event_id)


@router.get("/reality/replay-determinism")
def replay_determinism(
	branch: str | None = None,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.replay_determinism(branch=branch)


@router.get("/reality/branch-verification")
def verify_branch_replay(
	branch: str | None = None,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.verify_branch_replay(branch=branch)


@router.get("/reality/snapshot-integrity/{snapshot_id}")
def verify_snapshot_integrity(
	snapshot_id: str,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.verify_snapshot_integrity(snapshot_id)


@router.post("/query")
def query_story(
	request: QueryRequest,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.query(request.query)


@router.get("/relationships/graph/{character_id}")
def relationship_graph_summary(
	character_id: str,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.relationship_summary(character_id)


@router.get("/relationships/graph")
def relationship_dimension_query(
	dimension: str,
	minimum: float = 0.5,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> list[dict[str, object]]:
	return state_engine.relationship_dimension(dimension=dimension, minimum=minimum)


@router.get("/knowledge-graph/summary")
def knowledge_graph_summary(
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.knowledge_graph_summary()


@router.get("/knowledge-graph/traverse")
def knowledge_graph_traverse(
	node_id: str,
	depth: int = 1,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.knowledge_graph_traverse(node_id=node_id, depth=depth)


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
