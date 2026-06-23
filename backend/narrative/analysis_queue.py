from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SceneAnalysisQueue:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self._root_dir = Path(root_dir or ".cache/scene_analysis_jobs")
        self._pending_dir = self._root_dir / "pending"
        self._processing_dir = self._root_dir / "processing"
        self._failed_dir = self._root_dir / "failed"
        self._pending_dir.mkdir(parents=True, exist_ok=True)
        self._processing_dir.mkdir(parents=True, exist_ok=True)
        self._failed_dir.mkdir(parents=True, exist_ok=True)

    def enqueue(self, scene_hash: str, payload: dict[str, Any]) -> bool:
        pending_path = self._pending_dir / f"{scene_hash}.json"
        processing_path = self._processing_dir / f"{scene_hash}.json"
        failed_path = self._failed_dir / f"{scene_hash}.json"
        if pending_path.exists() or processing_path.exists():
            return False
        failed_path.unlink(missing_ok=True)
        pending_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        return True

    def has_inflight(self, scene_hash: str) -> bool:
        return (self._pending_dir / f"{scene_hash}.json").exists() or (self._processing_dir / f"{scene_hash}.json").exists()

    def claim_next(self) -> tuple[Path, dict[str, Any]] | None:
        for path in sorted(self._pending_dir.glob("*.json")):
            processing_path = self._processing_dir / path.name
            try:
                path.replace(processing_path)
            except FileNotFoundError:
                continue
            payload = json.loads(processing_path.read_text(encoding="utf-8"))
            return processing_path, payload
        return None

    def complete(self, processing_path: Path) -> None:
        processing_path.unlink(missing_ok=True)

    def fail(self, processing_path: Path, error: str) -> None:
        payload = json.loads(processing_path.read_text(encoding="utf-8"))
        payload["last_error"] = error
        payload["status"] = "failed"
        failed_path = self._failed_dir / processing_path.name
        failed_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        processing_path.unlink(missing_ok=True)