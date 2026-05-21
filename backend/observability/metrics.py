from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from time import perf_counter


@dataclass(slots=True)
class MetricsRegistry:
	counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
	timings: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

	def increment(self, name: str, amount: int = 1) -> int:
		self.counters[name] += amount
		return self.counters[name]

	def observe(self, name: str, value: float) -> float:
		self.timings[name].append(value)
		return value

	def timer(self, name: str):
		started = perf_counter()

		class _Timer:
			def __enter__(self_inner):
				return self_inner

			def __exit__(self_inner, exc_type, exc, tb):
				self.observe(name, perf_counter() - started)

		return _Timer()


metrics = MetricsRegistry()
