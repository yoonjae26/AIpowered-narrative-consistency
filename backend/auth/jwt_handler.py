from dataclasses import dataclass, field
from typing import Any

from backend.core.security import create_access_token, create_refresh_token, decode_token


@dataclass(slots=True)
class TokenPair:
	access_token: str
	refresh_token: str
	token_type: str = "bearer"
	metadata: dict[str, Any] = field(default_factory=dict)


def issue_token_pair(subject: str, scopes: list[str] | None = None) -> TokenPair:
	return TokenPair(
		access_token=create_access_token(subject, scopes=scopes),
		refresh_token=create_refresh_token(subject),
	)


def validate_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
	payload = decode_token(token)
	if expected_type is not None and payload.get("type") != expected_type:
		raise ValueError("Unexpected token type")
	return payload
