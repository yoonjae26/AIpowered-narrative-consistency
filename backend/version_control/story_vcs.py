from __future__ import annotations

from dataclasses import asdict
from typing import Any

from backend.narrative.reality import deterministic_replay_report, state_checksum
from backend.version_control.branch_manager import BranchManager
from backend.version_control.diff_engine import DiffEngine
from backend.version_control.event_store import EventStore, StoredNarrativeEvent
from backend.version_control.snapshot_manager import Snapshot, SnapshotManager


class StoryVersionControl:
    """Git-like facade over narrative events, snapshots, diffs, and branches."""

    def __init__(
        self,
        event_store: EventStore | None = None,
        snapshot_manager: SnapshotManager | None = None,
        branch_manager: BranchManager | None = None,
        diff_engine: DiffEngine | None = None,
    ) -> None:
        self.events = event_store or EventStore()
        self.snapshots = snapshot_manager or SnapshotManager()
        self.branches = branch_manager or BranchManager()
        self.diff = diff_engine or DiffEngine()
        if self.branches.current_branch() is None:
            self.branches.create_branch("main")

    def current_branch(self) -> str:
        current = self.branches.current_branch()
        return current.name if current else "main"

    def append_commit(self, title: str, events: list[Any], derived_state: dict[str, Any]) -> dict[str, Any]:
        branch = self.current_branch()
        stored_events = self.events.append_events(events, branch=branch)
        replay_state = self.replay(branch=branch)
        replay_checksum = state_checksum(replay_state)
        snapshot = self.create_snapshot(
            title=title,
            branch=branch,
            derived_state=replay_state or derived_state,
            latest_event_id=stored_events[-1].id if stored_events else None,
            derived_state_checksum=replay_checksum,
        )
        self.branches.set_head(branch, snapshot.id, stored_events[-1].id if stored_events else None)
        return {
            "branch": branch,
            "event_ids": [event.id for event in stored_events],
            "snapshot_id": snapshot.id,
            "derived_state": replay_state or derived_state,
            "derived_state_checksum": replay_checksum,
        }

    def create_snapshot(
        self,
        title: str,
        branch: str,
        derived_state: dict[str, Any],
        latest_event_id: str | None,
        derived_state_checksum: str | None = None,
    ) -> Snapshot:
        return self.snapshots.create_snapshot(
            title=title,
            content=self._stringify_state(derived_state),
            branch=branch,
            latest_event_id=latest_event_id,
            derived_state=derived_state,
            derived_state_checksum=derived_state_checksum or state_checksum(derived_state),
        )

    def create_branch(self, name: str, from_branch: str | None = None) -> dict[str, Any]:
        source = self.branches.current_branch().name if self.branches.current_branch() and from_branch is None else (from_branch or "main")
        head_snapshot = self.branches.get_branch(source)
        branch = self.branches.create_branch(
            name,
            snapshot_id=head_snapshot.snapshot_id if head_snapshot else None,
            from_branch=source,
            fork_event_id=head_snapshot.head_event_id if head_snapshot else None,
        )
        return asdict(branch)

    def merge_branch(self, source_branch: str, target_branch: str | None = None) -> dict[str, Any] | None:
        target = target_branch or self.current_branch()
        if source_branch == target:
            return {
                "source_branch": source_branch,
                "target_branch": target,
                "merged_event_ids": [],
                "message": "Source and target branch are identical.",
            }
        source = self.branches.get_branch(source_branch)
        target_obj = self.branches.get_branch(target)
        if source is None or target_obj is None:
            return None

        target_origins = self._event_origins(target)
        candidates = [
            event for event in self.events.list_events(branch=source_branch)
            if (event.origin_event_id or event.id) not in target_origins
        ]
        merged = self.events.append_stored_events(candidates, branch=target, operation="merge")
        replay_state = self.replay(branch=target)
        snapshot = self.create_snapshot(
            title=f"Merge {source_branch} into {target}",
            branch=target,
            derived_state=replay_state,
            latest_event_id=merged[-1].id if merged else target_obj.head_event_id,
        )
        self.branches.set_head(target, snapshot.id, merged[-1].id if merged else target_obj.head_event_id)
        return {
            "source_branch": source_branch,
            "target_branch": target,
            "merged_event_ids": [event.id for event in merged],
            "snapshot_id": snapshot.id,
            "derived_state": replay_state,
        }

    def cherry_pick(self, source_branch: str, event_ids: list[str], target_branch: str | None = None) -> dict[str, Any] | None:
        target = target_branch or self.current_branch()
        if not event_ids:
            return {
                "source_branch": source_branch,
                "target_branch": target,
                "picked_event_ids": [],
                "message": "No event ids supplied.",
            }
        branch_obj = self.branches.get_branch(target)
        if self.branches.get_branch(source_branch) is None or branch_obj is None:
            return None

        lookup = {event.id: event for event in self.events.list_events(branch=source_branch)}
        target_origins = self._event_origins(target)
        selected = [lookup[event_id] for event_id in event_ids if event_id in lookup]
        selected = [event for event in selected if (event.origin_event_id or event.id) not in target_origins]
        picked = self.events.append_stored_events(selected, branch=target, operation="cherry-pick")
        replay_state = self.replay(branch=target)
        snapshot = self.create_snapshot(
            title=f"Cherry-pick from {source_branch} into {target}",
            branch=target,
            derived_state=replay_state,
            latest_event_id=picked[-1].id if picked else branch_obj.head_event_id,
        )
        self.branches.set_head(target, snapshot.id, picked[-1].id if picked else branch_obj.head_event_id)
        return {
            "source_branch": source_branch,
            "target_branch": target,
            "picked_event_ids": [event.id for event in picked],
            "snapshot_id": snapshot.id,
            "derived_state": replay_state,
        }

    def checkout(self, name: str) -> dict[str, Any] | None:
        branch = self.branches.checkout(name)
        return asdict(branch) if branch else None

    def rollback(self, snapshot_id: str) -> dict[str, Any] | None:
        snapshot = self.snapshots.get_snapshot(snapshot_id)
        if snapshot is None:
            return None
        branch = str(snapshot.metadata.get("branch") or self.current_branch())
        self.branches.set_head(branch, snapshot.id, snapshot.metadata.get("latest_event_id"))
        return {
            "branch": branch,
            "snapshot_id": snapshot.id,
            "content": snapshot.content,
            "metadata": snapshot.metadata,
        }

    def diff_snapshots(self, snapshot_a: str, snapshot_b: str) -> str:
        left = self.snapshots.get_snapshot(snapshot_a)
        right = self.snapshots.get_snapshot(snapshot_b)
        if left is None or right is None:
            return ""
        return self.diff.unified_diff(left.content, right.content, fromfile=left.title, tofile=right.title)

    def replay(self, branch: str | None = None, to_event_id: str | None = None) -> dict[str, Any]:
        branch_name = branch or self.current_branch()
        return self.events.replay_events(self._branch_events(branch_name), to_event_id=to_event_id)

    def replay_determinism_report(self, branch: str | None = None) -> dict[str, Any]:
        branch_name = branch or self.current_branch()
        branch_events = self._branch_events(branch_name)
        report = deterministic_replay_report(branch_events, self.events.replay_events)
        report["branch"] = branch_name
        return report

    def verify_snapshot_integrity(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.snapshots.get_snapshot(snapshot_id)
        if snapshot is None:
            return {"snapshot_id": snapshot_id, "valid": False, "reason": "snapshot_not_found"}

        metadata = dict(snapshot.metadata or {})
        derived_state = metadata.get("derived_state")
        expected_checksum = str(metadata.get("derived_state_checksum") or "")
        if not isinstance(derived_state, dict):
            return {
                "snapshot_id": snapshot_id,
                "valid": False,
                "reason": "derived_state_missing",
            }

        actual_checksum = state_checksum(derived_state)
        return {
            "snapshot_id": snapshot_id,
            "valid": actual_checksum == expected_checksum,
            "expected_checksum": expected_checksum,
            "actual_checksum": actual_checksum,
        }

    def verify_branch_replay(self, branch: str | None = None) -> dict[str, Any]:
        branch_name = branch or self.current_branch()
        replay_state = self.replay(branch=branch_name)
        replay_checksum = state_checksum(replay_state)
        branch_obj = self.branches.get_branch(branch_name)
        if branch_obj is None or not branch_obj.snapshot_id:
            return {
                "branch": branch_name,
                "valid": True,
                "reason": "no_head_snapshot",
                "replay_checksum": replay_checksum,
            }
        snapshot_status = self.verify_snapshot_integrity(branch_obj.snapshot_id)
        return {
            "branch": branch_name,
            "head_snapshot_id": branch_obj.snapshot_id,
            "replay_checksum": replay_checksum,
            "snapshot_integrity": snapshot_status,
            "valid": bool(snapshot_status.get("valid", False)) and replay_checksum == snapshot_status.get("actual_checksum"),
        }

    def list_snapshots(self) -> list[dict[str, Any]]:
        return [asdict(snapshot) for snapshot in self.snapshots.list_snapshots()]

    def list_branches(self) -> list[dict[str, Any]]:
        return [asdict(branch) for branch in self.branches.list_branches()]

    def _stringify_state(self, derived_state: dict[str, Any]) -> str:
        lines: list[str] = []
        lines.append("characters:")
        for name, data in sorted((derived_state.get("characters") or {}).items()):
            lines.append(f"- {name}: status={data.get('status')} location={data.get('last_location')}")
        lines.append("relationships:")
        for relation in derived_state.get("relationships") or []:
            lines.append(f"- {relation.get('source')} -> {relation.get('target')} ({relation.get('relationship_type')})")
        lines.append("scenes:")
        for scene in derived_state.get("scene_history") or []:
            lines.append(f"- {scene}")
        lines.append(f"event_count: {derived_state.get('event_count', 0)}")
        return "\n".join(lines)

    def _branch_events(self, branch: str) -> list[StoredNarrativeEvent]:
        branch_obj = self.branches.get_branch(branch)
        if branch_obj is None:
            return self.events.list_events(branch=branch)

        inherited: list[StoredNarrativeEvent] = []
        if branch_obj.from_branch:
            parent_events = self._branch_events(branch_obj.from_branch)
            if branch_obj.fork_event_id:
                for event in parent_events:
                    inherited.append(event)
                    if event.id == branch_obj.fork_event_id:
                        break
            else:
                inherited.extend(parent_events)

        current_events = self.events.list_events(branch=branch)
        return inherited + current_events

    def _event_origins(self, branch: str) -> set[str]:
        return {event.origin_event_id or event.id for event in self._branch_events(branch)}
