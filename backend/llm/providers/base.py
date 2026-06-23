from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LLMMessage:
	role: str
	content: str

	def as_payload(self) -> dict[str, str]:
		return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class LLMResponse:
	content: str
	metadata: dict[str, Any] = field(default_factory=dict)


class BaseLLMProvider(ABC):
	name: str = "base"

	@abstractmethod
	def complete(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
		raise NotImplementedError
