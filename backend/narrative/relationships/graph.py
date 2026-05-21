from dataclasses import dataclass, field

from backend.database.repositories.relationship_repository import RelationshipRepository
from backend.narrative.relationships.relationship_types import RelationshipType


@dataclass(slots=True)
class RelationshipEdge:
	source: str
	target: str
	relationship_type: RelationshipType
	strength: float = 0.5
	notes: list[str] = field(default_factory=list)


class RelationshipGraph:
	def __init__(self, repository: RelationshipRepository) -> None:
		self.repository = repository

	def add_relationship(self, source: str, target: str, relationship_type: RelationshipType, strength: float = 0.5, note: str | None = None) -> RelationshipEdge:
		created = self.repository.create(
			source=source,
			target=target,
			relationship_type=relationship_type.value,
			strength=strength,
			notes=[note] if note else [],
		)
		return RelationshipEdge(
			source=created.source,
			target=created.target,
			relationship_type=RelationshipType(created.relationship_type),
			strength=created.strength,
			notes=created.notes,
		)

	def list_relationships(self, character_id: str | None = None) -> list[RelationshipEdge]:
		return [
			RelationshipEdge(
				source=item.source,
				target=item.target,
				relationship_type=RelationshipType(item.relationship_type),
				strength=item.strength,
				notes=item.notes,
			)
			for item in self.repository.list(character_id=character_id)
		]
