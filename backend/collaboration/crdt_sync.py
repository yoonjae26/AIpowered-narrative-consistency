from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CRDTOperation:
	actor_id: str
	target_id: str
	payload: dict[str, object]
	vector_clock: dict[str, int] = field(default_factory=dict)


class CRDTSync:
	def merge(self, operations: list[CRDTOperation]) -> dict[str, object]:
		merged: dict[str, object] = {}
		for operation in operations:
			merged.update(operation.payload)
		return merged
