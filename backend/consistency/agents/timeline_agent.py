from __future__ import annotations


class TimelineAgent:
	def analyze(self, events: list[str]) -> list[str]:
		ordered = sorted(events)
		return [f"{index + 1}. {event}" for index, event in enumerate(ordered)]
