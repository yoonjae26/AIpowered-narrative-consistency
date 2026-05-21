from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.core.constants import CharacterRole, DEFAULT_CHARACTER_STATUS


class CharacterState(BaseModel):
	id: str = Field(default_factory=lambda: uuid4().hex)
	name: str
	role: CharacterRole = CharacterRole.SUPPORTING
	traits: list[str] = Field(default_factory=list)
	goals: list[str] = Field(default_factory=list)
	background: str | None = None
	status: str = DEFAULT_CHARACTER_STATUS
	metadata: dict[str, Any] = Field(default_factory=dict)
	created_at: datetime = Field(default_factory=datetime.utcnow)
	updated_at: datetime = Field(default_factory=datetime.utcnow)


class CharacterUpdate(BaseModel):
	name: str | None = None
	role: CharacterRole | None = None
	traits: list[str] | None = None
	goals: list[str] | None = None
	background: str | None = None
	status: str | None = None
	metadata: dict[str, Any] | None = None
