from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		payload = {
			"timestamp": datetime.now(UTC).isoformat(),
			"level": record.levelname,
			"logger": record.name,
			"message": record.getMessage(),
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
