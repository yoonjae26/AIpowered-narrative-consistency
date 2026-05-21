from dataclasses import dataclass, field
from datetime import datetime

from backend.database.repositories.timeline_repository import TimelineRepository


@dataclass(slots=True)
class TimelineEvent:
	id: str
	title: str
	description: str | None = None
	happened_at: datetime = field(default_factory=datetime.utcnow)
	metadata: dict[str, object] = field(default_factory=dict)


class TimelineTracker:
	def __init__(self, repository: TimelineRepository) -> None:
		self.repository = repository

	def add_event(self, event: TimelineEvent) -> TimelineEvent:
		created = self.repository.create(
			title=event.title,
			description=event.description,
			happened_at=event.happened_at,
			metadata=event.metadata,
		)
		return TimelineEvent(
			id=created.id,
			title=created.title,
			description=created.description,
			happened_at=created.happened_at,
			metadata=created.metadata_json,
		)

	def list_events(self) -> list[TimelineEvent]:
		return [
			TimelineEvent(
				id=item.id,
				title=item.title,
				description=item.description,
				happened_at=item.happened_at,
				metadata=item.metadata_json,
			)
			for item in self.repository.list()
		]
