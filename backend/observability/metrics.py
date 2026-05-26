from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass(slots=True)
class MetricsRegistry:
	counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
	timings: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
	gauges: dict[str, float] = field(default_factory=dict)

	def increment(self, name: str, amount: int = 1) -> int:
		self.counters[name] += amount
		return self.counters[name]

	def observe(self, name: str, value: float) -> float:
		self.timings[name].append(value)
		return value

	def set_gauge(self, name: str, value: float) -> float:
		self.gauges[name] = value
		return value

	def timer(self, name: str):
		started = perf_counter()

		class _Timer:
			def __enter__(self_inner):
				return self_inner

			def __exit__(self_inner, exc_type, exc, tb):
				self.observe(name, perf_counter() - started)

		return _Timer()


@dataclass(slots=True)
class ConsistencyMetrics:
	timeline_accuracy: float
	character_consistency: float
	canon_integrity: float
	overall_consistency: float

	def as_dict(self) -> dict[str, float]:
		return {
			"timeline_accuracy": round(self.timeline_accuracy, 4),
			"character_consistency": round(self.character_consistency, 4),
			"canon_integrity": round(self.canon_integrity, 4),
			"overall_consistency": round(self.overall_consistency, 4),
		}


def compute_consistency_metrics(payload: dict[str, Any]) -> ConsistencyMetrics:
	timeline = payload.get("timeline") or {}
	consistency = payload.get("consistency") or {}
	drift = payload.get("drift") or {}
	canon = payload.get("canon_protection") or {}
	semantic = payload.get("semantic_validation") or {}

	timeline_conflicts = len(timeline.get("conflicts") or [])
	flashback_penalty = min(0.15, 0.03 * int(timeline.get("flashback_count") or 0))
	timeline_accuracy = max(0.0, 1.0 - min(0.8, 0.2 * timeline_conflicts) - flashback_penalty)

	drift_issues = drift.get("issues") or []
	semantic_issues = semantic.get("issues") or []
	consistency_errors = len(consistency.get("errors") or [])
	character_consistency = max(
		0.0,
		1.0 - min(0.8, 0.2 * len(drift_issues)) - min(0.35, 0.05 * len(semantic_issues)) - min(0.2, 0.05 * consistency_errors),
	)

	canon_conflicts = canon.get("conflicts") or []
	error_conflicts = [item for item in canon_conflicts if str(item.get("severity", "")).lower() == "error"]
	canon_integrity = max(0.0, 1.0 - min(0.8, 0.35 * len(error_conflicts)) - min(0.2, 0.05 * len(canon_conflicts)))

	overall = max(0.0, min(1.0, (timeline_accuracy + character_consistency + canon_integrity) / 3.0))

	return ConsistencyMetrics(
		timeline_accuracy=timeline_accuracy,
		character_consistency=character_consistency,
		canon_integrity=canon_integrity,
		overall_consistency=overall,
	)


def record_token_usage(provider: str, usage: dict[str, int] | None) -> None:
	if usage is None:
		return
	prompt_tokens = int(usage.get("prompt_tokens") or 0)
	completion_tokens = int(usage.get("completion_tokens") or 0)
	total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))

	metrics.increment("llm.calls.total", 1)
	metrics.increment(f"llm.calls.{provider}", 1)
	metrics.increment("llm.tokens.prompt", prompt_tokens)
	metrics.increment("llm.tokens.completion", completion_tokens)
	metrics.increment("llm.tokens.total", total_tokens)
	metrics.increment(f"llm.tokens.{provider}", total_tokens)


def metric_snapshot() -> dict[str, Any]:
	return {
		"counters": dict(metrics.counters),
		"timings": {key: list(values) for key, values in metrics.timings.items()},
		"gauges": dict(metrics.gauges),
	}


metrics = MetricsRegistry()
