from backend.database.repositories.character_repository import CharacterRepository
from backend.narrative.character.models import CharacterState, CharacterUpdate


class CharacterManager:
	def __init__(self, repository: CharacterRepository) -> None:
		self.repository = repository

	def create_character(self, character: CharacterState) -> CharacterState:
		created = self.repository.create(
			character_id=character.id,
			name=character.name,
			role=character.role.value,
			traits=character.traits,
			goals=character.goals,
			background=character.background,
			status=character.status,
			metadata=character.metadata,
		)
		return CharacterState(
			id=created.id,
			name=created.name,
			role=created.role,
			traits=created.traits,
			goals=created.goals,
			background=created.background,
			status=created.status,
			metadata=created.metadata_json,
			created_at=created.created_at,
			updated_at=created.updated_at,
		)

	def upsert_character(self, character_id: str, update: CharacterUpdate) -> CharacterState:
		patch = update.model_dump(exclude_unset=True)
		if "role" in patch and patch["role"] is not None:
			patch["role"] = patch["role"].value
		updated = self.repository.upsert(character_id, patch)
		return CharacterState(
			id=updated.id,
			name=updated.name,
			role=updated.role,
			traits=updated.traits,
			goals=updated.goals,
			background=updated.background,
			status=updated.status,
			metadata=updated.metadata_json,
			created_at=updated.created_at,
			updated_at=updated.updated_at,
		)

	def get_character(self, character_id: str) -> CharacterState | None:
		item = self.repository.get(character_id)
		if item is None:
			return None
		return CharacterState(
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

	def list_characters(self) -> list[CharacterState]:
		return [self.get_character(item.id) for item in self.repository.list() if self.get_character(item.id) is not None]

	def delete_character(self, character_id: str) -> bool:
		item = self.repository.get(character_id)
		if item is None:
			return False
		self.repository.db.delete(item)
		self.repository.db.commit()
		return True
