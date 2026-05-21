from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SemanticValidationResult:
	score: float
	notes: list[str]


class SemanticValidator:
	def validate(self, text: str, references: list[str]) -> SemanticValidationResult:
		overlap = sum(1 for reference in references if reference.lower() in text.lower())
		score = overlap / max(1, len(references))
		notes = [f"Matched {overlap} of {len(references)} references."] if references else ["No references supplied."]
		return SemanticValidationResult(score=score, notes=notes)
