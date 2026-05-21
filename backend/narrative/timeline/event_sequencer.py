from backend.narrative.timeline.tracker import TimelineEvent


class EventSequencer:
	def sequence(self, events: list[TimelineEvent]) -> list[TimelineEvent]:
		return sorted(events, key=lambda event: event.happened_at)

	def group_by_title(self, events: list[TimelineEvent]) -> dict[str, list[TimelineEvent]]:
		grouped: dict[str, list[TimelineEvent]] = {}
		for event in self.sequence(events):
			grouped.setdefault(event.title, []).append(event)
		return grouped
