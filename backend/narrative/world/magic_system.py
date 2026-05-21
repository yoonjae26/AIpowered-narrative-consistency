from dataclasses import dataclass, field

from backend.database.repositories.magic_repository import MagicRepository


@dataclass(slots=True)
class MagicRule:
	name: str
	description: str
	cost: str | None = None
	limitations: list[str] = field(default_factory=list)


class MagicSystem:
	def __init__(self, repository: MagicRepository) -> None:
		self.repository = repository

	def add_rule(self, name: str, description: str, cost: str | None = None, limitations: list[str] | None = None) -> MagicRule:
		rule = self.repository.upsert(name=name, description=description, cost=cost, limitations=limitations or [])
		return MagicRule(name=rule.name, description=rule.description, cost=rule.cost, limitations=rule.limitations)

	def describe(self) -> list[MagicRule]:
		return [
			MagicRule(name=rule.name, description=rule.description, cost=rule.cost, limitations=rule.limitations)
			for rule in self.repository.list()
		]
