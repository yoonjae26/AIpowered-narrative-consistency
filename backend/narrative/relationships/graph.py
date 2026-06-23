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
	dimensions: dict[str, float] = field(default_factory=dict)


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
			dimensions=self._dimensions(RelationshipType(created.relationship_type), created.strength),
		)

	def list_relationships(self, character_id: str | None = None) -> list[RelationshipEdge]:
		edges: list[RelationshipEdge] = []
		for item in self.repository.list(character_id=character_id):
			try:
				rel_type = RelationshipType(item.relationship_type)
			except ValueError:
				rel_type = RelationshipType.ALLY  # fallback for legacy/invalid types
			edges.append(RelationshipEdge(
				source=item.source,
				target=item.target,
				relationship_type=rel_type,
				strength=item.strength,
				notes=item.notes,
				dimensions=self._dimensions(rel_type, item.strength),
			))
		return edges

	def relationship_between(self, source: str, target: str) -> RelationshipEdge | None:
		for edge in self.list_relationships():
			if edge.source == source and edge.target == target:
				return edge
			if edge.source == target and edge.target == source:
				return edge
		return None

	def neighbors(self, character_id: str) -> list[RelationshipEdge]:
		return [edge for edge in self.list_relationships() if edge.source == character_id or edge.target == character_id]

	def query_by_dimension(self, dimension: str, minimum: float = 0.5) -> list[RelationshipEdge]:
		matches: list[RelationshipEdge] = []
		for edge in self.list_relationships():
			if edge.dimensions.get(dimension, 0.0) >= minimum:
				matches.append(edge)
		return matches

	def summary(self, character_id: str) -> dict[str, object]:
		edges = self.neighbors(character_id)
		return {
			"character": character_id,
			"connections": len(edges),
			"allies": [edge.target if edge.source == character_id else edge.source for edge in edges if edge.relationship_type == RelationshipType.ALLY],
			"enemies": [edge.target if edge.source == character_id else edge.source for edge in edges if edge.relationship_type == RelationshipType.ENEMY],
			"romantic": [edge.target if edge.source == character_id else edge.source for edge in edges if edge.relationship_type == RelationshipType.ROMANTIC],
		}

	def _dimensions(self, relationship_type: RelationshipType, strength: float) -> dict[str, float]:
		trust = 0.0
		friendship = 0.0
		hatred = 0.0
		alliance = 0.0
		if relationship_type == RelationshipType.ALLY:
			trust = strength
			friendship = strength * 0.8
			alliance = strength
		elif relationship_type == RelationshipType.ENEMY:
			hatred = strength
			trust = 0.0
		elif relationship_type == RelationshipType.FAMILY:
			trust = max(strength, 0.7)
			friendship = strength * 0.6
		elif relationship_type == RelationshipType.ROMANTIC:
			trust = strength * 0.9
			friendship = strength
		elif relationship_type == RelationshipType.MENTOR:
			trust = strength
			alliance = strength * 0.5
		elif relationship_type == RelationshipType.RIVAL:
			hatred = strength * 0.6
			friendship = strength * 0.2
		return {
			"trust": round(trust, 4),
			"friendship": round(friendship, 4),
			"hatred": round(hatred, 4),
			"alliance": round(alliance, 4),
		}
