from dataclasses import dataclass, field


@dataclass(slots=True)
class BeatSheet:
	scene_id: str
	beats: list[str] = field(default_factory=list)

	def add_beat(self, beat: str) -> None:
		self.beats.append(beat)

	def to_outline(self) -> list[str]:
		return [f"{index + 1}. {beat}" for index, beat in enumerate(self.beats)]
