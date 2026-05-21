from dataclasses import dataclass, field

from backend.database.repositories.canon_repository import CanonRepository


@dataclass(slots=True)
class CanonEntry:
	key: str
	value: str
	immutable: bool = True
	aliases: set[str] = field(default_factory=set)


class CanonRegistry:
	def __init__(self, repository: CanonRepository) -> None:
		self.repository = repository

	def register(self, key: str, value: str, immutable: bool = True, aliases: set[str] | None = None) -> CanonEntry:
		entry = self.repository.upsert(key=key, value=value, immutable=immutable, aliases=sorted(aliases or set()))
		return CanonEntry(key=entry.key, value=entry.value, immutable=entry.immutable, aliases=set(entry.aliases))

	def get(self, key: str) -> CanonEntry | None:
		entry = self.repository.get(key)
		if entry is None:
			return None
		return CanonEntry(key=entry.key, value=entry.value, immutable=entry.immutable, aliases=set(entry.aliases))

	def validate(self, key: str, value: str) -> tuple[bool, str | None]:
		entry = self.get(key)
		if entry is None:
			return True, None
		if entry.immutable and entry.value != value:
			return False, f"Canon conflict for {key}: expected {entry.value!r}, got {value!r}"
		return True, None
