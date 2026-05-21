from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PermissionRule:
	user_id: str
	resource_id: str
	actions: set[str] = field(default_factory=set)


class PermissionManager:
	def __init__(self) -> None:
		self._rules: list[PermissionRule] = []

	def grant(self, user_id: str, resource_id: str, actions: set[str]) -> PermissionRule:
		rule = PermissionRule(user_id=user_id, resource_id=resource_id, actions=set(actions))
		self._rules.append(rule)
		return rule

	def can(self, user_id: str, resource_id: str, action: str) -> bool:
		return any(rule.user_id == user_id and rule.resource_id == resource_id and action in rule.actions for rule in self._rules)
