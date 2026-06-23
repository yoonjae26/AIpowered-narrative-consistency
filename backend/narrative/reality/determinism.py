from __future__ import annotations

import hashlib
import json
from typing import Any


def event_order_key(event: Any) -> tuple[str, str, str]:
    return (
        str(getattr(event, "happened_at", "") or ""),
        str(getattr(event, "recorded_at", "") or ""),
        str(getattr(event, "id", "") or ""),
    )


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonicalize(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        canonical_items = [_canonicalize(item) for item in value]
        if all(isinstance(item, (str, int, float, bool)) or item is None for item in canonical_items):
            return canonical_items
        return sorted(canonical_items, key=lambda item: json.dumps(item, ensure_ascii=True, sort_keys=True))
    return value


def state_checksum(state: dict[str, Any]) -> str:
    canonical = _canonicalize(state)
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deterministic_replay_report(events: list[Any], replay_fn) -> dict[str, Any]:
    ordered = sorted(events, key=event_order_key)
    state_original = replay_fn(list(events))
    state_ordered = replay_fn(ordered)

    checksum_original = state_checksum(state_original)
    checksum_ordered = state_checksum(state_ordered)

    return {
        "event_count": len(events),
        "ordering_applied": [getattr(item, "id", "") for item in ordered],
        "checksum_original": checksum_original,
        "checksum_ordered": checksum_ordered,
        "deterministic": checksum_original == checksum_ordered,
    }
