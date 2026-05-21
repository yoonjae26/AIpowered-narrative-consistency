from enum import Enum


class Environment(str, Enum):
	DEVELOPMENT = "development"
	TESTING = "testing"
	STAGING = "staging"
	PRODUCTION = "production"


class ProjectStatus(str, Enum):
	DRAFT = "draft"
	ACTIVE = "active"
	ARCHIVED = "archived"


class CharacterRole(str, Enum):
	PROTAGONIST = "protagonist"
	ANTAGONIST = "antagonist"
	SUPPORTING = "supporting"
	EXTRA = "extra"


class ConsistencySeverity(str, Enum):
	INFO = "info"
	WARNING = "warning"
	ERROR = "error"


DEFAULT_PROJECT_TITLE = "Untitled Narrative"
DEFAULT_CHARACTER_STATUS = "active"
