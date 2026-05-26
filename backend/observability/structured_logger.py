from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		extra = {
			key: value
			for key, value in record.__dict__.items()
			if key not in {
				"name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
				"exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
				"relativeCreated", "thread", "threadName", "processName", "process", "message",
			}
		}
		payload = {
			"timestamp": datetime.now(UTC).isoformat(),
			"level": record.levelname,
			"logger": record.name,
			"message": record.getMessage(),
			"extra": extra,
		}
		return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: int = logging.INFO) -> None:
	handler = logging.StreamHandler()
	handler.setFormatter(JsonFormatter())
	root = logging.getLogger()
	root.handlers.clear()
	root.addHandler(handler)
	root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
	return logging.getLogger(name)


def log_prompt_event(
	logger: logging.Logger,
	provider: str,
	model: str,
	prompt: str,
	completion: str,
	metadata: dict[str, Any] | None = None,
) -> None:
	logger.info(
		"llm_prompt_event",
		extra={
			"provider": provider,
			"model": model,
			"prompt_preview": prompt[:500],
			"completion_preview": completion[:500],
			"metadata": metadata or {},
		},
	)
