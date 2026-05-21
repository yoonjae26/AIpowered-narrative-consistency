from __future__ import annotations

from pydantic import BaseModel, Field


class PageSchema(BaseModel):
	items: list[object] = Field(default_factory=list)
	total: int = 0


class OperationResult(BaseModel):
	ok: bool = True
	message: str | None = None
