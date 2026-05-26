from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"
    SCENE = "scene"


class EntityLifecycleStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


CHARACTER_SUBJECT_EVENT_TYPES: set[str] = {
    "character_appears",
    "character_exits",
    "character_changes",
    "death",
    "murder",
    "injury",
    "birth",
    "resurrection",
    "marriage",
    "betrayal",
    "alliance",
    "conflict",
    "discovery",
    "travel",
    "capture",
    "escape",
    "relationship_forms",
    "relationship_changes",
}

CHARACTER_TARGET_EVENT_TYPES: set[str] = {
    "murder",
    "injury",
    "marriage",
    "betrayal",
    "alliance",
    "conflict",
    "capture",
    "relationship_forms",
    "relationship_changes",
    "discovery",
}

RELATIONSHIP_EVENT_TYPES: set[str] = {
    "alliance",
    "betrayal",
    "relationship_forms",
    "relationship_changes",
    "marriage",
    "conflict",
}


@dataclass(slots=True)
class TypedEntity:
    entity_id: str
    name: str
    entity_type: EntityType
    lifecycle: EntityLifecycleStatus = EntityLifecycleStatus.ACTIVE
    attributes: dict[str, Any] = field(default_factory=dict)
    first_seen_event: str | None = None
    last_seen_event: str | None = None
    version: int = 1


@dataclass(slots=True)
class TypedEvent:
    event_id: str
    event_type: str
    subject: str
    subject_type: EntityType
    predicate: str
    target: str | None = None
    target_type: EntityType | None = None
    location: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TypedRelationshipEdge:
    source: str
    target: str
    edge_type: str
    weight: float
    evidence_event_ids: list[str] = field(default_factory=list)


class EntityRegistry:
    def __init__(self) -> None:
        self._entities: dict[str, TypedEntity] = {}

    def _key(self, name: str, entity_type: EntityType) -> str:
        return f"{entity_type.value}:{name.strip().lower()}"

    def register(self, name: str, entity_type: EntityType, event_id: str | None = None, attributes: dict[str, Any] | None = None) -> TypedEntity:
        key = self._key(name, entity_type)
        existing = self._entities.get(key)
        if existing is None:
            item = TypedEntity(
                entity_id=key,
                name=name,
                entity_type=entity_type,
                attributes=dict(attributes or {}),
                first_seen_event=event_id,
                last_seen_event=event_id,
            )
            self._entities[key] = item
            return item

        existing.last_seen_event = event_id or existing.last_seen_event
        if attributes:
            existing.attributes.update(attributes)
        existing.lifecycle = EntityLifecycleStatus.ACTIVE
        existing.version += 1
        return existing

    def mark_deleted(self, name: str, entity_type: EntityType, event_id: str | None = None) -> None:
        key = self._key(name, entity_type)
        existing = self._entities.get(key)
        if existing is None:
            existing = self.register(name, entity_type, event_id=event_id)
        existing.lifecycle = EntityLifecycleStatus.DELETED
        existing.last_seen_event = event_id or existing.last_seen_event
        existing.version += 1

    def list_entities(self) -> list[TypedEntity]:
        return sorted(self._entities.values(), key=lambda item: (item.entity_type.value, item.name.lower()))

    def as_payload(self) -> dict[str, Any]:
        entities = [
            {
                "entity_id": item.entity_id,
                "name": item.name,
                "entity_type": item.entity_type.value,
                "lifecycle": item.lifecycle.value,
                "attributes": dict(item.attributes),
                "first_seen_event": item.first_seen_event,
                "last_seen_event": item.last_seen_event,
                "version": item.version,
            }
            for item in self.list_entities()
        ]
        counts: dict[str, int] = {}
        for entity in entities:
            counts[entity["entity_type"]] = counts.get(entity["entity_type"], 0) + 1
        return {"entities": entities, "counts": counts}


def infer_subject_type(event_type: str) -> EntityType:
    if event_type in CHARACTER_SUBJECT_EVENT_TYPES:
        return EntityType.CHARACTER
    if event_type in {"scene_opens", "scene_closes"}:
        return EntityType.SCENE
    if event_type == "world_state_change":
        return EntityType.LOCATION
    return EntityType.CONCEPT


def infer_target_type(event_type: str, target: str | None) -> EntityType | None:
    if not target:
        return None
    if event_type in CHARACTER_TARGET_EVENT_TYPES:
        return EntityType.CHARACTER
    if event_type in {"travel", "world_state_change"}:
        return EntityType.LOCATION
    return EntityType.CONCEPT


def validate_typed_event(event: TypedEvent) -> list[str]:
    errors: list[str] = []
    if not event.subject.strip():
        errors.append("subject_must_not_be_empty")
    if not event.predicate.strip():
        errors.append("predicate_must_not_be_empty")
    if event.event_type in {"murder", "injury", "alliance", "betrayal", "marriage", "conflict"} and not event.target:
        errors.append("target_required_for_event_type")
    if event.event_type == "travel" and not event.location:
        errors.append("location_recommended_for_travel")
    if event.subject_type == EntityType.SCENE and event.event_type not in {"scene_opens", "scene_closes"}:
        errors.append("scene_subject_only_allowed_for_scene_events")
    return errors


def relationship_edge_for_event(event: TypedEvent) -> TypedRelationshipEdge | None:
    if event.event_type not in RELATIONSHIP_EVENT_TYPES or not event.target:
        return None
    weight = float(event.attributes.get("strength", 0.5) or 0.5)
    weight = max(0.0, min(1.0, weight))
    return TypedRelationshipEdge(
        source=event.subject,
        target=event.target,
        edge_type=event.event_type,
        weight=weight,
        evidence_event_ids=[event.event_id],
    )
