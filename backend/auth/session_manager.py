from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4


@dataclass(slots=True)
class SessionRecord:
	session_id: str
	user_id: str
	token: str
	created_at: datetime
	expires_at: datetime
	revoked: bool = False
	metadata: dict[str, object] = field(default_factory=dict)

	@property
	def is_active(self) -> bool:
		return not self.revoked and self.expires_at > datetime.now(UTC)


class SessionManager:
	def __init__(self) -> None:
		self._sessions: dict[str, SessionRecord] = {}

	def create_session(self, user_id: str, token: str, ttl_minutes: int = 60 * 24, **metadata: object) -> SessionRecord:
		now = datetime.now(UTC)
		record = SessionRecord(
			session_id=uuid4().hex,
			user_id=user_id,
			token=token,
			created_at=now,
			expires_at=now + timedelta(minutes=ttl_minutes),
			metadata=dict(metadata),
		)
		self._sessions[record.session_id] = record
		return record

	def get_session(self, session_id: str) -> SessionRecord | None:
		return self._sessions.get(session_id)

	def revoke_session(self, session_id: str) -> bool:
		session = self._sessions.get(session_id)
		if session is None:
			return False
		session.revoked = True
		return True

	def revoke_token(self, token: str) -> bool:
		for session in self._sessions.values():
			if session.token == token:
				session.revoked = True
				return True
		return False

	def active_sessions(self, user_id: str | None = None) -> list[SessionRecord]:
		sessions = [session for session in self._sessions.values() if session.is_active]
		if user_id is not None:
			sessions = [session for session in sessions if session.user_id == user_id]
		return sessions


session_manager = SessionManager()
