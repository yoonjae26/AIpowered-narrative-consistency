from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass(slots=True)
class Branch:
	name: str
	snapshot_id: str | None = None
	head_event_id: str | None = None
	from_branch: str | None = None
	fork_event_id: str | None = None
	metadata: dict[str, object] = field(default_factory=dict)


class BranchManager:
	def __init__(self, file_path: str | Path | None = None) -> None:
		self._file_path = Path(file_path or ".cache/narrative_branches.json")
		self._file_path.parent.mkdir(parents=True, exist_ok=True)
		self._branches: dict[str, Branch] = {}
		self._active_branch: str | None = None
		self._load()

	def create_branch(self, name: str, snapshot_id: str | None = None, **metadata: object) -> Branch:
		branch = Branch(
			name=name,
			snapshot_id=snapshot_id,
			head_event_id=metadata.pop("head_event_id", None),
			from_branch=metadata.pop("from_branch", None),
			fork_event_id=metadata.pop("fork_event_id", None),
			metadata=dict(metadata),
		)
		self._branches[name] = branch
		if self._active_branch is None:
			self._active_branch = name
		self._persist()
		return branch

	def checkout(self, name: str) -> Branch | None:
		if name in self._branches:
			self._active_branch = name
			self._persist()
		return self._branches.get(name)

	def current_branch(self) -> Branch | None:
		if self._active_branch is None:
			return None
		return self._branches.get(self._active_branch)

	def list_branches(self) -> list[Branch]:
		return list(self._branches.values())

	def get_branch(self, name: str) -> Branch | None:
		return self._branches.get(name)

	def set_head(self, name: str, snapshot_id: str | None, event_id: str | None) -> None:
		branch = self._branches.get(name)
		if branch is None:
			branch = self.create_branch(name, snapshot_id=snapshot_id, head_event_id=event_id)
		else:
			branch.snapshot_id = snapshot_id
			branch.head_event_id = event_id
			self._persist()

	def _persist(self) -> None:
		payload = {
			"active_branch": self._active_branch,
			"branches": [
				{
					"name": branch.name,
					"snapshot_id": branch.snapshot_id,
					"head_event_id": branch.head_event_id,
					"from_branch": branch.from_branch,
					"fork_event_id": branch.fork_event_id,
					"metadata": branch.metadata,
				}
				for branch in self._branches.values()
			],
		}
		self._file_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

	def _load(self) -> None:
		if not self._file_path.exists():
			return
		payload = json.loads(self._file_path.read_text(encoding="utf-8"))
		self._active_branch = payload.get("active_branch")
		for item in payload.get("branches", []):
			branch = Branch(
				name=item["name"],
				snapshot_id=item.get("snapshot_id"),
				head_event_id=item.get("head_event_id"),
				from_branch=item.get("from_branch"),
				fork_event_id=item.get("fork_event_id"),
				metadata=dict(item.get("metadata", {})),
			)
			self._branches[branch.name] = branch
