from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Branch:
	name: str
	snapshot_id: str | None = None
	metadata: dict[str, object] = field(default_factory=dict)


class BranchManager:
	def __init__(self) -> None:
		self._branches: dict[str, Branch] = {}
		self._active_branch: str | None = None

	def create_branch(self, name: str, snapshot_id: str | None = None, **metadata: object) -> Branch:
		branch = Branch(name=name, snapshot_id=snapshot_id, metadata=dict(metadata))
		self._branches[name] = branch
		if self._active_branch is None:
			self._active_branch = name
		return branch

	def checkout(self, name: str) -> Branch | None:
		if name in self._branches:
			self._active_branch = name
		return self._branches.get(name)

	def current_branch(self) -> Branch | None:
		if self._active_branch is None:
			return None
		return self._branches.get(self._active_branch)

	def list_branches(self) -> list[Branch]:
		return list(self._branches.values())
