from dataclasses import dataclass, field

from backend.database.repositories.lore_repository import LoreRepository


@dataclass(slots=True)
class LoreFact:
	key: str
	value: str
	source: str | None = None
	tags: set[str] = field(default_factory=set)


class LoreManager:
	def __init__(self, repository: LoreRepository) -> None:
		self.repository = repository

	def add_fact(self, key: str, value: str, source: str | None = None, tags: set[str] | None = None) -> LoreFact:
		created = self.repository.upsert(key, value, source, sorted(tags or set()))
		return LoreFact(key=created.key, value=created.value, source=created.source, tags=set(created.tags))

	def get_fact(self, key: str) -> LoreFact | None:
		fact = self.repository.get(key)
		if fact is None:
			return None
		return LoreFact(key=fact.key, value=fact.value, source=fact.source, tags=set(fact.tags))

	def list_facts(self) -> list[LoreFact]:
		return [LoreFact(key=fact.key, value=fact.value, source=fact.source, tags=set(fact.tags)) for fact in self.repository.list()]

	def search(self, query: str) -> list[LoreFact]:
		return [LoreFact(key=fact.key, value=fact.value, source=fact.source, tags=set(fact.tags)) for fact in self.repository.search(query)]
