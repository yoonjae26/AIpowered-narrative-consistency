from enum import Enum


class RelationshipType(str, Enum):
	ALLY = "ally"
	ENEMY = "enemy"
	FAMILY = "family"
	ROMANTIC = "romantic"
	MENTOR = "mentor"
	RIVAL = "rival"
