from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4


@dataclass(slots=True)
class Snapshot:
	id: str
	title: str
	content: str
	created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
	metadata: dict[str, object] = field(default_factory=dict)


class SnapshotManager:
	def __init__(self, file_path: str | Path | None = None) -> None:
		self._file_path = Path(file_path or ".cache/narrative_snapshots.json")
		self._file_path.parent.mkdir(parents=True, exist_ok=True)
		self._snapshots: dict[str, Snapshot] = {}
		self._load()

	def create_snapshot(self, title: str, content: str, **metadata: object) -> Snapshot:
		snapshot = Snapshot(id=uuid4().hex, title=title, content=content, metadata=dict(metadata))
		self._snapshots[snapshot.id] = snapshot
		self._persist()
		return snapshot

	def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
		return self._snapshots.get(snapshot_id)

	def list_snapshots(self) -> list[Snapshot]:
		return list(self._snapshots.values())

	def _persist(self) -> None:
		payload = [
			{
				"id": snapshot.id,
				"title": snapshot.title,
				"content": snapshot.content,
				"created_at": snapshot.created_at.isoformat(),
				"metadata": snapshot.metadata,
			}
			for snapshot in self._snapshots.values()
		]
		self._file_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

	def _load(self) -> None:
		if not self._file_path.exists():
			return
		payload = json.loads(self._file_path.read_text(encoding="utf-8"))
		for item in payload:
			snapshot = Snapshot(
				id=item["id"],
				title=item["title"],
				content=item["content"],
				created_at=datetime.fromisoformat(item["created_at"]),
				metadata=dict(item.get("metadata", {})),
			)
			self._snapshots[snapshot.id] = snapshot
