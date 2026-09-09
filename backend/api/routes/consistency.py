from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.consistency.checkers.regulation_checker import ContentRegulationChecker
from backend.consistency.checkers.symbolic_engine import SymbolicConsistencyEngine
from backend.core.constants import ConsistencySeverity
from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.relationship_repository import RelationshipRepository


router = APIRouter(prefix="/consistency", tags=["consistency"])


class ConsistencyCheckRequest(BaseModel):
	narrative: str = Field(min_length=1)
	reference_notes: list[str] = Field(default_factory=list)


class ConsistencyIssue(BaseModel):
	severity: ConsistencySeverity
	code: str
	message: str
	entities: list[str] = Field(default_factory=list)
	evidence: list[str] = Field(default_factory=list)
	rule: str = ""


def _check_for_simple_conflicts(text: str, reference_notes: list[str]) -> list[ConsistencyIssue]:
	issues: list[ConsistencyIssue] = []
	lowered = text.lower()
	if "always" in lowered and "never" in lowered:
		issues.append(ConsistencyIssue(
			severity=ConsistencySeverity.WARNING,
			code="opposite_absolutes",
			message="Text contains both absolute and negating language.",
		))
	if len(reference_notes) > 20:
		issues.append(ConsistencyIssue(
			severity=ConsistencySeverity.INFO,
			code="many_references",
			message="Large reference set may reduce precision.",
		))
	return issues


@router.post("/check")
def check_consistency(
	request: ConsistencyCheckRequest,
	db: Session = Depends(get_db),
) -> dict[str, object]:
	simple_issues = _check_for_simple_conflicts(request.narrative, request.reference_notes)

	characters = CharacterRepository(db, commit_on_write=False).list()
	relationships = RelationshipRepository(db, commit_on_write=False).list()
	engine = SymbolicConsistencyEngine(characters, relationships)
	symbolic = engine.check(request.narrative)

	sym_issues = [
		ConsistencyIssue(
			severity=ConsistencySeverity(issue.severity),
			code=issue.code,
			message=issue.message,
			entities=issue.entities,
			evidence=issue.evidence,
			rule=issue.rule,
		)
		for issue in symbolic
	]

	regulations = ContentRegulationChecker().check(request.narrative)

	all_issues = simple_issues + sym_issues
	return {
		"issues": [i.model_dump() for i in all_issues],
		"issue_count": len(all_issues),
		"regulations": [
			{
				"level": r.level,
				"category": r.category,
				"code": r.code,
				"message": r.message,
				"evidence": r.evidence,
			}
			for r in regulations
		],
		"regulation_count": len(regulations),
		"has_error_violations": any(r.level == "error" for r in regulations),
	}
