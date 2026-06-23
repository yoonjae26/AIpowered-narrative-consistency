from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from backend.core.config import get_settings

try:
	from langfuse import Langfuse
except Exception:  # pragma: no cover - optional dependency fallback
	Langfuse = None


@dataclass(slots=True)
class NullLangfuseClient:
	def trace(self, *args, **kwargs):
		return None

	def observe(self, *args, **kwargs):
		return None

	def flush(self, *args, **kwargs):
		return None


@dataclass(slots=True)
class TraceSession:
	name: str
	trace_id: str
	started_at: str
	metadata: dict[str, Any] = field(default_factory=dict)
	latency_ms: float | None = None


def _now_iso() -> str:
	return datetime.now(UTC).isoformat()


class LangfuseClient:
	def __init__(self) -> None:
		settings = get_settings()
		if Langfuse is None or not settings.langfuse_public_key or not settings.langfuse_secret_key:
			self._client = NullLangfuseClient()
		else:
			self._client = Langfuse(public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key)

	@property
	def client(self):
		return self._client

	def start_trace(self, name: str, input_payload: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> TraceSession:
		trace_id = f"{name}:{datetime.now(UTC).timestamp():.6f}"
		session = TraceSession(
			name=name,
			trace_id=trace_id,
			started_at=_now_iso(),
			metadata=dict(metadata or {}),
		)
		try:
			self._safe_call("trace", name=name, input=input_payload or {}, metadata=session.metadata)
		except Exception:
			pass
		return session

	def record_span(
		self,
		session: TraceSession,
		name: str,
		input_payload: dict[str, Any] | None = None,
		output_payload: dict[str, Any] | None = None,
		metadata: dict[str, Any] | None = None,
	) -> None:
		payload = {
			"trace_id": session.trace_id,
			"span_name": name,
			"at": _now_iso(),
			"input": input_payload or {},
			"output": output_payload or {},
			"metadata": {**session.metadata, **(metadata or {})},
		}
		self._safe_call("event", **payload)
		self._safe_call("observe", **payload)

	def log_generation(
		self,
		provider: str,
		model: str,
		prompt: str,
		completion: str,
		usage: dict[str, int] | None = None,
		metadata: dict[str, Any] | None = None,
	) -> None:
		payload = {
			"provider": provider,
			"model": model,
			"prompt": prompt,
			"completion": completion,
			"usage": usage or {},
			"metadata": metadata or {},
			"at": _now_iso(),
		}
		self._safe_call("event", name="llm_generation", input=payload)
		self._safe_call("observe", name="llm_generation", input=payload)

	def finish_trace(self, session: TraceSession, output_payload: dict[str, Any] | None = None, level: str = "INFO") -> TraceSession:
		start = datetime.fromisoformat(session.started_at)
		session.latency_ms = round((datetime.now(UTC) - start).total_seconds() * 1000, 3)
		payload = {
			"trace_id": session.trace_id,
			"name": session.name,
			"latency_ms": session.latency_ms,
			"output": output_payload or {},
			"level": level,
			"metadata": session.metadata,
		}
		self._safe_call("event", name="trace_finished", input=payload)
		self._safe_call("observe", name="trace_finished", input=payload)
		self._safe_call("flush")
		return session

	def trace_timer(self, name: str, metadata: dict[str, Any] | None = None):
		outer = self
		started = perf_counter()
		session = self.start_trace(name=name, metadata=metadata)

		class _TraceTimer:
			def __enter__(self_inner):
				return session

			def __exit__(self_inner, exc_type, exc, tb):
				latency_ms = round((perf_counter() - started) * 1000, 3)
				outer.finish_trace(
					session,
					output_payload={
						"ok": exc_type is None,
						"latency_ms": latency_ms,
						"error": str(exc) if exc else None,
					},
					level="ERROR" if exc else "INFO",
				)

		return _TraceTimer()

	def _safe_call(self, method_name: str, **kwargs: Any) -> Any:
		method = getattr(self._client, method_name, None)
		if callable(method):
			try:
				return method(**kwargs)
			except TypeError:
				return method(kwargs)
		return None
