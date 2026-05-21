from dataclasses import dataclass, field
from datetime import datetime

from backend.database.repositories.scene_repository import SceneRepository


@dataclass(slots=True)
class Scene:
	id: str
	title: str
	summary: str | None = None
	beats: list[str] = field(default_factory=list)
	characters: list[str] = field(default_factory=list)
	created_at: datetime = field(default_factory=datetime.utcnow)


class SceneManager:
	def __init__(self, repository: SceneRepository) -> None:
		self.repository = repository

	def create_scene(self, scene: Scene) -> Scene:
		created = self.repository.create(
			title=scene.title,
			summary=scene.summary,
			beats=scene.beats,
			characters=scene.characters,
		)
		return Scene(
			id=created.id,
			title=created.title,
			summary=created.summary,
			beats=created.beats,
			characters=created.characters,
			created_at=created.created_at,
		)

	def list_scenes(self) -> list[Scene]:
		return [
			Scene(
				id=item.id,
				title=item.title,
				summary=item.summary,
				beats=item.beats,
				characters=item.characters,
				created_at=item.created_at,
			)
			for item in self.repository.list()
		]

	def get_scene(self, scene_id: str) -> Scene | None:
		for item in self.repository.list():
			if item.id == scene_id:
				return Scene(
					id=item.id,
					title=item.title,
					summary=item.summary,
					beats=item.beats,
					characters=item.characters,
					created_at=item.created_at,
				)
		return None
