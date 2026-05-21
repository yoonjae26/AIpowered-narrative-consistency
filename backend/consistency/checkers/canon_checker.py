from __future__ import annotations

from dataclasses import dataclass

from backend.narrative.world.canon_registry import CanonRegistry


@dataclass(slots=True)
class CanonIssue:
	key: str
	message: str


class CanonChecker:
	def __init__(self, registry: CanonRegistry) -> None:
		self.registry = registry

	def check_entry(self, key: str, value: str) -> list[CanonIssue]:
		valid, message = self.registry.validate(key, value)
		if valid:
			return []
		return [CanonIssue(key=key, message=message or "Canon conflict")]
