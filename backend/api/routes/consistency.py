from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.core.constants import ConsistencySeverity


router = APIRouter(prefix="/consistency", tags=["consistency"])


class ConsistencyCheckRequest(BaseModel):
	narrative: str = Field(min_length=1)
	reference_notes: list[str] = Field(default_factory=list)


class ConsistencyIssue(BaseModel):
	severity: ConsistencySeverity
	code: str
	message: str


def _check_for_simple_conflicts(text: str, reference_notes: list[str]) -> list[ConsistencyIssue]:
	issues: list[ConsistencyIssue] = []
	lowered = text.lower()
	if "always" in lowered and "never" in lowered:
		issues.append(ConsistencyIssue(severity=ConsistencySeverity.WARNING, code="opposite_absolutes", message="Text contains both absolute and negating language."))
	if len(reference_notes) > 20:
		issues.append(ConsistencyIssue(severity=ConsistencySeverity.INFO, code="many_references", message="Large reference set may reduce precision."))
	return issues


@router.post("/check")
def check_consistency(request: ConsistencyCheckRequest) -> dict[str, object]:
	issues = _check_for_simple_conflicts(request.narrative, request.reference_notes)
	return {"issues": [issue.model_dump() for issue in issues], "issue_count": len(issues)}
