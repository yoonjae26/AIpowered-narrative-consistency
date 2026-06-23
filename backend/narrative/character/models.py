from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.core.constants import CharacterRole, DEFAULT_CHARACTER_STATUS


class CharacterPBKD(BaseModel):
	personality: list[str] = Field(default_factory=list)
	beliefs: list[str] = Field(default_factory=list)
	knowledge: list[str] = Field(default_factory=list)
	desires: list[str] = Field(default_factory=list)


class CharacterState(BaseModel):
	id: str = Field(default_factory=lambda: uuid4().hex)
	name: str
	role: CharacterRole = CharacterRole.SUPPORTING
	traits: list[str] = Field(default_factory=list)
	goals: list[str] = Field(default_factory=list)
	pbkd: CharacterPBKD = Field(default_factory=CharacterPBKD)
	background: str | None = None
	status: str = DEFAULT_CHARACTER_STATUS
	metadata: dict[str, Any] = Field(default_factory=dict)
	created_at: datetime = Field(
    default_factory=lambda: datetime.now(UTC))
	updated_at: datetime = Field(
    default_factory=lambda: datetime.now(UTC))


class CharacterUpdate(BaseModel):
	name: str | None = None
	role: CharacterRole | None = None
	traits: list[str] | None = None
	goals: list[str] | None = None
	pbkd: CharacterPBKD | None = None
	background: str | None = None
	status: str | None = None
	metadata: dict[str, Any] | None = None
