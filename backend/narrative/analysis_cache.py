from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock
from time import time
from typing import Any


def build_scene_analysis_hash(
    scene_text: str,
    scene_title: str | None,
    branch: str,
    references: list[str] | None = None,
) -> str:
    payload = {
        "scene_text": " ".join(scene_text.split()),
        "scene_title": (scene_title or "").strip(),
        "branch": branch.strip(),
        "references": [" ".join(item.split()) for item in (references or [])],
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")).hexdigest()
    return digest


class SceneAnalysisCache:
    def __init__(
        self,
        file_path: str | Path | None = None,
        ttl_seconds: int = 3600,
        policy_signature: str = "default",
    ) -> None:
        self._file_path = Path(file_path or ".cache/scene_analysis_cache.json")
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._policy_signature = policy_signature
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def get(self, scene_hash: str) -> dict[str, Any] | None:
        entry = self._entries.get(scene_hash)
        if entry is None:
            return None
        if not self._is_valid(entry):
            with self._lock:
                self._entries.pop(scene_hash, None)
                self._persist()
            return None
        public_entry = {
            key: value
            for key, value in entry.items()
            if not str(key).startswith("_")
        }
        return json.loads(json.dumps(public_entry))

    def set(self, scene_hash: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._entries[scene_hash] = self._with_metadata(payload)
            self._persist()

    def mark_pending(self, scene_hash: str) -> None:
        with self._lock:
            current = dict(self._entries.get(scene_hash) or {})
            current["status"] = "pending"
            self._entries[scene_hash] = self._with_metadata(current)
            self._persist()

    def has(self, scene_hash: str) -> bool:
        return self.get(scene_hash) is not None

    def invalidate(self, scene_hash: str) -> None:
        with self._lock:
            self._entries.pop(scene_hash, None)
            self._persist()

    def _with_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = int(time())
        data = json.loads(json.dumps(payload))
        data["_created_at"] = now
        data["_expires_at"] = now + self._ttl_seconds
        data["_policy_signature"] = self._policy_signature
        return data

    def _is_valid(self, entry: dict[str, Any]) -> bool:
        expires_at = int(entry.get("_expires_at") or 0)
        policy_signature = str(entry.get("_policy_signature") or "")
        if policy_signature != self._policy_signature:
            return False
        if expires_at and expires_at < int(time()):
            return False
        return True

    def _persist(self) -> None:
        self._file_path.write_text(json.dumps(self._entries, ensure_ascii=True, sort_keys=True), encoding="utf-8")

    def _load(self) -> None:
        if not self._file_path.exists():
            return
        try:
            self._entries = json.loads(self._file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._entries = {}