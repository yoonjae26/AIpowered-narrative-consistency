from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from backend.llm.providers.base import BaseLLMProvider, LLMMessage
from backend.narrative.mutation.models import EventType, NarrativeEvent


@dataclass(slots=True)
class SemanticIssue:
	rule_id: str
	category: str
	severity: str
	message: str
	evidence: list[str] = field(default_factory=list)
	entities: list[str] = field(default_factory=list)
	source: str = "heuristic"


@dataclass(slots=True)
class SemanticValidationResult:
	score: float
	issues: list[SemanticIssue] = field(default_factory=list)
	notes: list[str] = field(default_factory=list)
	provider_used: str | None = None


class SemanticValidator:
	def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
		self._llm = llm_provider

	def validate(
		self,
		text: str,
		references: list[str] | None = None,
		events: list[NarrativeEvent] | None = None,
		character_memories: dict[str, Any] | None = None,
	) -> SemanticValidationResult:
		references = references or []
		events = events or []
		issues = self._heuristic_issues(text, events, references, character_memories or {})
		notes = [self._reference_note(text, references)]
		provider_used = None

		if self._llm is not None:
			try:
				llm_issues = self._llm_issues(text, references, events)
				issues.extend(llm_issues)
				provider_used = self._llm.name
				notes.append(f"LLM semantic pass contributed {len(llm_issues)} findings.")
			except Exception as exc:
				notes.append(f"LLM semantic pass unavailable: {exc}")

		deduped = self._dedupe(issues)
		score = self._score(deduped)
		if not deduped:
			notes.append("No semantic narrative issues detected.")
		return SemanticValidationResult(
			score=score,
			issues=deduped,
			notes=notes,
			provider_used=provider_used,
		)

	def _heuristic_issues(
		self,
		text: str,
		events: list[NarrativeEvent],
		references: list[str],
		character_memories: dict[str, Any],
	) -> list[SemanticIssue]:
		issues: list[SemanticIssue] = []
		issues.extend(self._emotional_mismatch(text, events, character_memories))
		issues.extend(self._dialogue_inconsistency(text, references, character_memories))
		issues.extend(self._unnatural_progression(text, events))
		return issues

	def _emotional_mismatch(
		self,
		text: str,
		events: list[NarrativeEvent],
		character_memories: dict[str, Any],
	) -> list[SemanticIssue]:
		lowered = text.lower()
		tragic = {EventType.DEATH, EventType.MURDER, EventType.INJURY, EventType.BETRAYAL, EventType.CAPTURE}
		celebratory = {EventType.MARRIAGE, EventType.ALLIANCE, EventType.BIRTH, EventType.RESURRECTION}
		joyful_markers = ("laughed", "smiled", "cheerful", "delighted", "grinned", "joyfully")
		grief_markers = ("sobbed", "wept", "grief", "mourned", "despair", "shaking")
		issues: list[SemanticIssue] = []

		if any(marker in lowered for marker in joyful_markers) and any(event.event_type in tragic for event in events):
			entities = sorted({event.subject for event in events if event.event_type in tragic and event.subject})
			issues.append(SemanticIssue(
				rule_id="semantic_emotional_mismatch",
				category="emotional_mismatch",
				severity="warning",
				message="The scene pairs joyful emotional language with a tragic beat without enough justification.",
				evidence=[text[:200]],
				entities=entities,
			))

		if any(marker in lowered for marker in grief_markers) and any(event.event_type in celebratory for event in events):
			entities = sorted({event.subject for event in events if event.event_type in celebratory and event.subject})
			issues.append(SemanticIssue(
				rule_id="semantic_emotional_mismatch",
				category="emotional_mismatch",
				severity="warning",
				message="The scene signals grief during a celebratory progression and may need a clearer emotional bridge.",
				evidence=[text[:200]],
				entities=entities,
			))

		for name, memory in character_memories.items():
			personality = {item.lower() for item in getattr(memory, "personality", [])}
			if any(item.startswith("emotion:joy") or item.startswith("emotion:happy") for item in personality) and any(event.event_type in tragic for event in events):
				issues.append(SemanticIssue(
					rule_id="semantic_emotional_mismatch",
					category="emotional_mismatch",
					severity="warning",
					message=f"{name}'s stored emotional state looks upbeat compared with the violent turn in this scene.",
					evidence=list(personality),
					entities=[name],
				))
		return issues

	def _dialogue_inconsistency(
		self,
		text: str,
		references: list[str],
		character_memories: dict[str, Any],
	) -> list[SemanticIssue]:
		quotes = re.findall(r'["“](.+?)["”]', text, re.DOTALL)
		claims: dict[tuple[str, str], set[bool]] = {}
		evidence: list[str] = []
		pattern = re.compile(
			r"\bI\s+(?P<neg>never\s+|do not\s+|don't\s+|cannot\s+|can't\s+)?(?P<verb>trust|love|hate|know|remember|serve|forgive)\s+(?P<object>[A-Z][a-zA-Z\-]+)\b",
			re.IGNORECASE,
		)
		for quote in quotes:
			for match in pattern.finditer(quote):
				key = (match.group("verb").lower(), match.group("object"))
				claims.setdefault(key, set()).add(bool(match.group("neg")))
				evidence.append(match.group(0))

		issues: list[SemanticIssue] = []
		contradictory_pairs = [key for key, values in claims.items() if len(values) > 1]
		if contradictory_pairs:
			objects = [obj for _, obj in contradictory_pairs]
			issues.append(SemanticIssue(
				rule_id="dialogue_inconsistency",
				category="dialogue_inconsistency",
				severity="warning",
				message="Dialogue makes conflicting claims about the same relationship or fact inside the scene.",
				evidence=evidence,
				entities=objects,
			))

		lowered_quotes = " ".join(quotes).lower()
		for name, memory in character_memories.items():
			beliefs = {item.lower() for item in getattr(memory, "beliefs", [])}
			if any("never kill" in belief for belief in beliefs) and any(token in lowered_quotes for token in ("kill", "murder", "love killing")):
				issues.append(SemanticIssue(
					rule_id="dialogue_inconsistency",
					category="dialogue_inconsistency",
					severity="warning",
					message=f"{name}'s dialogue conflicts with their established beliefs.",
					evidence=list(beliefs)[:3] + quotes[:2],
					entities=[name],
				))

		if not quotes and references:
			return issues
		return issues

	def _unnatural_progression(self, text: str, events: list[NarrativeEvent]) -> list[SemanticIssue]:
		if len(events) < 2:
			return []
		bridge_pattern = re.compile(r"\b(after|later|because|by then|the next day|meanwhile|despite|although|once|eventually)\b", re.IGNORECASE)
		high_intensity = {
			EventType.MURDER,
			EventType.DEATH,
			EventType.BETRAYAL,
			EventType.CAPTURE,
			EventType.ESCAPE,
			EventType.RESURRECTION,
			EventType.MARRIAGE,
			EventType.ALLIANCE,
		}
		major_events = [event for event in events if event.event_type in high_intensity]
		issues: list[SemanticIssue] = []

		transitional_pairs = {
			(EventType.MURDER, EventType.MARRIAGE),
			(EventType.MURDER, EventType.ALLIANCE),
			(EventType.DEATH, EventType.MARRIAGE),
			(EventType.DEATH, EventType.ALLIANCE),
			(EventType.BETRAYAL, EventType.MARRIAGE),
			(EventType.BETRAYAL, EventType.ALLIANCE),
		}
		for previous, current in zip(events, events[1:]):
			if (previous.event_type, current.event_type) in transitional_pairs and not bridge_pattern.search(text):
				issues.append(SemanticIssue(
					rule_id="unnatural_progression",
					category="unnatural_progression",
					severity="warning",
					message="The scene jumps from a severe turn into a stabilizing beat without enough connective tissue.",
					evidence=[previous.predicate, current.predicate],
					entities=[item for item in [previous.subject, previous.target, current.subject, current.target] if item],
				))
				break

		if len(major_events) >= 3 and not bridge_pattern.search(text):
			issues.append(SemanticIssue(
				rule_id="unnatural_progression",
				category="unnatural_progression",
				severity="warning",
				message="Several major plot turns happen back-to-back and may feel unnaturally compressed.",
				evidence=[event.predicate for event in major_events[:4]],
				entities=sorted({event.subject for event in major_events if event.subject}),
			))

		if text.lower().count("suddenly") >= 2:
			issues.append(SemanticIssue(
				rule_id="unnatural_progression",
				category="unnatural_progression",
				severity="info",
				message="Repeated 'suddenly' cues suggest the scene may be forcing progression instead of earning it.",
				evidence=[text[:200]],
			))

		return issues

	def _llm_issues(
		self,
		text: str,
		references: list[str],
		events: list[NarrativeEvent],
	) -> list[SemanticIssue]:
		event_lines = [f"- {event.event_type.value}: {event.predicate}" for event in events]
		prompt = "\n".join([
			"Scene:",
			text,
			"",
			"Reference notes:",
			*(references or ["- none"]),
			"",
			"Events:",
			*(event_lines or ["- none"]),
			"",
			"Return ONLY a JSON array of issues with keys: category, severity, message, evidence, entities.",
			"Allowed categories: emotional_mismatch, dialogue_inconsistency, unnatural_progression.",
		])
		response = self._llm.complete([
			LLMMessage(role="system", content="You are a semantic narrative validator. Detect subtle emotional mismatch, dialogue inconsistency, and unnatural progression. Return JSON only."),
			LLMMessage(role="user", content=prompt),
		])
		return self._parse_llm_payload(response.content)

	def _parse_llm_payload(self, raw: str) -> list[SemanticIssue]:
		cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
		try:
			payload = json.loads(cleaned)
		except json.JSONDecodeError:
			match = re.search(r"\[.*\]", cleaned, re.DOTALL)
			if match is None:
				return []
			payload = json.loads(match.group(0))

		issues: list[SemanticIssue] = []
		for item in payload:
			category = str(item.get("category") or "unnatural_progression")
			issues.append(SemanticIssue(
				rule_id=self._rule_id_for(category),
				category=category,
				severity=str(item.get("severity") or "warning"),
				message=str(item.get("message") or "LLM flagged a semantic issue."),
				evidence=[str(part) for part in item.get("evidence", [])],
				entities=[str(part) for part in item.get("entities", [])],
				source="llm",
			))
		return issues

	def _reference_note(self, text: str, references: list[str]) -> str:
		overlap = sum(1 for reference in references if reference.lower() in text.lower())
		if references:
			return f"Matched {overlap} of {len(references)} reference notes verbatim in the scene text."
		return "No references supplied."

	def _rule_id_for(self, category: str) -> str:
		mapping = {
			"emotional_mismatch": "semantic_emotional_mismatch",
			"dialogue_inconsistency": "dialogue_inconsistency",
			"unnatural_progression": "unnatural_progression",
		}
		return mapping.get(category, "unnatural_progression")

	def _dedupe(self, issues: list[SemanticIssue]) -> list[SemanticIssue]:
		deduped: list[SemanticIssue] = []
		seen: set[tuple[str, str]] = set()
		for issue in issues:
			key = (issue.rule_id, issue.message.lower())
			if key in seen:
				continue
			seen.add(key)
			deduped.append(issue)
		return deduped

	def _score(self, issues: list[SemanticIssue]) -> float:
		penalty = 0.0
		for issue in issues:
			penalty += 0.3 if issue.severity == "error" else 0.15 if issue.severity == "warning" else 0.05
		return round(max(0.0, 1.0 - penalty), 4)
