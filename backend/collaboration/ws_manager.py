from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Connection:
	connection_id: str
	user_id: str | None = None
	metadata: dict[str, object] = field(default_factory=dict)


class WebSocketManager:
	def __init__(self) -> None:
		self._connections: dict[str, Connection] = {}

	def add(self, connection: Connection) -> Connection:
		self._connections[connection.connection_id] = connection
		return connection

	def remove(self, connection_id: str) -> bool:
		return self._connections.pop(connection_id, None) is not None

	def list_connections(self) -> list[Connection]:
		return list(self._connections.values())
