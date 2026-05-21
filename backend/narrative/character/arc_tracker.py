from dataclasses import dataclass, field

from backend.database.repositories.arc_repository import ArcRepository


@dataclass(slots=True)
class ArcProgress:
	character_id: str
	milestone: str
	progress: float = 0.0
	notes: list[str] = field(default_factory=list)


class ArcTracker:
	def __init__(self, repository: ArcRepository) -> None:
		self.repository = repository

	def mark_milestone(self, character_id: str, milestone: str, progress: float, note: str | None = None) -> ArcProgress:
		existing = self.repository.get(character_id)
		notes = list(existing.notes) if existing is not None else []
		if note:
			notes.append(note)
		record = self.repository.upsert(
			character_id=character_id,
			milestone=milestone,
			progress=max(0.0, min(1.0, progress)),
			notes=notes,
		)
		return ArcProgress(character_id=record.character_id, milestone=record.milestone, progress=record.progress, notes=record.notes)

	def get_progress(self, character_id: str) -> ArcProgress | None:
		record = self.repository.get(character_id)
		if record is None:
			return None
		return ArcProgress(character_id=record.character_id, milestone=record.milestone, progress=record.progress, notes=record.notes)
