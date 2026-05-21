from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class OAuthIdentity:
	provider: str
	subject: str
	email: str | None = None
	display_name: str | None = None
	access_token: str | None = None
	refresh_token: str | None = None


class OAuthProvider(Protocol):
	name: str

	def exchange_code(self, code: str, redirect_uri: str | None = None) -> OAuthIdentity:
		...


class DummyOAuthProvider:
	name = "dummy"

	def exchange_code(self, code: str, redirect_uri: str | None = None) -> OAuthIdentity:
		return OAuthIdentity(provider=self.name, subject=code, display_name="Demo User")
