from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(slots=True)
class Snapshot:
	id: str
	title: str
	content: str
	created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
	metadata: dict[str, object] = field(default_factory=dict)


class SnapshotManager:
	def __init__(self) -> None:
		self._snapshots: dict[str, Snapshot] = {}

	def create_snapshot(self, title: str, content: str, **metadata: object) -> Snapshot:
		snapshot = Snapshot(id=uuid4().hex, title=title, content=content, metadata=dict(metadata))
		self._snapshots[snapshot.id] = snapshot
		return snapshot

	def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
		return self._snapshots.get(snapshot_id)

	def list_snapshots(self) -> list[Snapshot]:
		return list(self._snapshots.values())
