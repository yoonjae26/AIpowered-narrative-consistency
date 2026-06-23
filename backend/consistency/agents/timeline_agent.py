from __future__ import annotations

from typing import Any

from backend.llm.providers.base import BaseLLMProvider, LLMMessage


class TimelineAgent:
	def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
		self._llm = llm_provider

	def analyze(
		self,
		events: list[Any],
		scene_text: str = "",
		chronology_conflicts: list[str] | None = None,
		flashback_count: int = 0,
		flash_forward_count: int = 0,
	) -> list[str]:
		findings = list(chronology_conflicts or [])
		if flashback_count:
			findings.append(f"Scene includes {flashback_count} flashback beat(s); chronology should stay explicit.")
		if flash_forward_count:
			findings.append(f"Scene includes {flash_forward_count} flash-forward beat(s); foreshadowing may need anchoring.")
		if not findings and events:
			findings.append(f"Reviewed {len(events)} events and found no direct chronology conflict.")

		if self._llm is not None:
			try:
				event_lines = [getattr(event, "predicate", str(event)) for event in events]
				prompt = "\n".join([
					f"Scene: {scene_text}",
					"Events:",
					*event_lines,
					f"Chronology conflicts: {chronology_conflicts or []}",
					"Return short bullet findings about chronology and order.",
				])
				response = self._llm.complete([
					LLMMessage(role="system", content="You are a timeline-focused narrative analyst."),
					LLMMessage(role="user", content=prompt),
				])
				findings.extend(line.strip("- ") for line in response.content.splitlines() if line.strip())
			except Exception:
				pass

		return list(dict.fromkeys(findings))
