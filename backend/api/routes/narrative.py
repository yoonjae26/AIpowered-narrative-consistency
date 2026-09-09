import json
import re
from datetime import datetime, UTC
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, status
from jose.jwt import UTC
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.database.repositories.canon_repository import CanonRepository
from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.relationship_repository import RelationshipRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.database.repositories.timeline_repository import TimelineRepository
from backend.core.constants import CharacterRole
from backend.narrative.character.models import CharacterPBKD, CharacterState, CharacterUpdate
from backend.narrative.response_formatter import format_mutation_api_response
from backend.narrative.relationships.relationship_types import RelationshipType
from backend.narrative.state_engine import NarrativeStateMutationEngine


router = APIRouter(prefix="/narrative", tags=["narrative"])


def _normalize_character_role(role: object) -> CharacterRole:
	value = str(role or "").strip().lower()
	legacy_map = {
		"hero": CharacterRole.PROTAGONIST,
		"main": CharacterRole.PROTAGONIST,
		"lead": CharacterRole.PROTAGONIST,
		"villain": CharacterRole.ANTAGONIST,
		"enemy": CharacterRole.ANTAGONIST,
		"support": CharacterRole.SUPPORTING,
		"sidekick": CharacterRole.SUPPORTING,
		"minor": CharacterRole.EXTRA,
		"background": CharacterRole.EXTRA,
	}
	if value in legacy_map:
		return legacy_map[value]
	try:
		return CharacterRole(value)
	except ValueError:
		return CharacterRole.SUPPORTING


def _normalize_pbkd(
	traits: list[str] | None,
	goals: list[str] | None,
	metadata: dict[str, object] | None,
) -> CharacterPBKD:
	meta = metadata or {}
	beliefs = [str(item) for item in (meta.get("beliefs") or [])]
	knowledge = [str(item) for item in (meta.get("knowledge") or [])]
	desires = [str(item) for item in (meta.get("desires") or goals or [])]
	personality = [str(item) for item in (traits or [])]
	return CharacterPBKD(
		personality=personality,
		beliefs=beliefs,
		knowledge=knowledge,
		desires=desires,
	)


def _merge_pbkd_to_fields(
	traits: list[str] | None,
	goals: list[str] | None,
	metadata: dict[str, object] | None,
	pbkd: CharacterPBKD | None,
) -> tuple[list[str], list[str], dict[str, object]]:
	meta = dict(metadata or {})
	next_traits = list(traits or [])
	next_goals = list(goals or [])
	if pbkd is not None:
		if pbkd.personality:
			next_traits = list(pbkd.personality)
		if pbkd.desires:
			next_goals = list(pbkd.desires)
		if pbkd.beliefs:
			meta["beliefs"] = list(pbkd.beliefs)
		if pbkd.knowledge:
			meta["knowledge"] = list(pbkd.knowledge)
		if pbkd.desires:
			meta["desires"] = list(pbkd.desires)
	return next_traits, next_goals, meta


class LoreFactCreate(BaseModel):
	key: str
	value: str
	source: str | None = None
	tags: set[str] = Field(default_factory=set)


class TimelineEventCreate(BaseModel):
	title: str
	description: str | None = None
	happened_at: datetime | None = None


class SceneCreate(BaseModel):
	title: str
	summary: str | None = None
	beats: list[str] = Field(default_factory=list)
	characters: list[str] = Field(default_factory=list)


class RelationshipCreate(BaseModel):
	source: str
	target: str
	relationship_type: RelationshipType
	strength: float = 0.5
	note: str | None = None

class SceneInput(BaseModel):
	scene_text: str
	scene_title: str | None = None
	context: dict = Field(default_factory=dict)


class BranchCreate(BaseModel):
	name: str
	from_branch: str | None = None


class BranchMergeRequest(BaseModel):
	source_branch: str
	target_branch: str | None = None


class CherryPickRequest(BaseModel):
	source_branch: str
	event_ids: list[str] = Field(default_factory=list)
	target_branch: str | None = None


class SnapshotRollbackRequest(BaseModel):
	snapshot_id: str


class QueryRequest(BaseModel):
	query: str
	character_filter: str | None = None


class RewriteRequest(BaseModel):
	source_text: str
	scene_title: str | None = None
	instructions: str | None = None
	target_tone: str | None = None
	max_length: int | None = Field(default=1200, ge=80, le=4000)
	preserve_characters: bool = True
	preserve_canon: bool = True
	style_notes: list[str] = Field(default_factory=list)


class StructuredAutoEditRequest(RewriteRequest):
	max_issues: int = Field(default=8, ge=1, le=16)
	candidates_per_issue: int = Field(default=3, ge=1, le=6)
	auto_apply: bool = False
	use_knowledge_graph_evidence: bool = True
	strict_reverification: bool = True
	pbkd_inferences: list[dict[str, object]] = Field(default_factory=list)
	kg_conflicts: list[dict[str, object]] = Field(default_factory=list)


class StructuredPatch(BaseModel):
	issue: str
	location: str
	replace: str
	with_text: str = Field(alias="with")
	rationale: str | None = None

	model_config = {
		"populate_by_name": True,
	}


class PatchDecision(BaseModel):
	patch_id: str
	action: Literal["accept", "reject", "edit"]
	edited_with: str | None = None


class StructuredPatchReviewRequest(RewriteRequest):
	decisions: list[PatchDecision] = Field(default_factory=list)
	patches: list[dict[str, object]] = Field(default_factory=list)
	strict_reverification: bool = True


def _fallback_rewrite_response(request: RewriteRequest, reason: str) -> dict[str, object]:
	return {
		"provider_used": None,
		"reason": reason,
		"rewritten_text": request.source_text,
		"summary": "대체 모드가 원본 장면 텍스트를 변경 없이 반환했습니다.",
		"suggestions": [
			"자동 재작성을 활성화하려면 LLM 제공자를 설정하세요.",
			"instructions 필드를 사용하여 문체, 어조, 구조를 조정하세요.",
		],
		"risk_notes": [],
	}


def _parse_rewrite_payload(content: str) -> dict[str, object]:
	candidate = content.strip()
	fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", candidate, re.DOTALL | re.IGNORECASE)
	if fenced:
		candidate = fenced.group(1).strip()
	else:
		json_start = candidate.find("{")
		json_end = candidate.rfind("}")
		if 0 <= json_start < json_end:
			candidate = candidate[json_start:json_end + 1]
	try:
		payload = json.loads(candidate)
		if isinstance(payload, dict):
			payload["rewritten_text"] = str(payload.get("rewritten_text") or payload.get("text") or "").strip()
			payload["summary"] = str(payload.get("summary") or "").strip()
			payload["suggestions"] = _as_string_list(payload.get("suggestions"))
			payload["risk_notes"] = _as_string_list(payload.get("risk_notes"))
			return payload
	except Exception:
		pass
	return {
		"rewritten_text": content.strip(),
		"summary": "모델이 JSON 형식이 아닌 응답을 반환했습니다.",
		"suggestions": [],
		"risk_notes": ["JSON 형식이 아닌 모델 출력이 원문 그대로 반환되었습니다."],
	}


def _as_string_list(value: object) -> list[str]:
	if value is None:
		return []
	if isinstance(value, list):
		return [str(item).strip() for item in value if str(item).strip()]
	if isinstance(value, str):
		text = value.strip()
		return [text] if text else []
	return [str(value).strip()] if str(value).strip() else []


def _split_paragraphs(text: str) -> list[str]:
	parts = [chunk.strip() for chunk in re.split(r"\n\s*\n", text.strip())]
	return [part for part in parts if part]


def _extract_knowledge_graph_evidence(text: str) -> list[dict[str, str]]:
	triples: list[dict[str, str]] = []
	patterns = [
		# 한국어 관계 패턴 (주요)
		(r"([가-힣]{2,6})(?:은|는|이|가)?[^.\n]{0,20}([가-힣]{2,6})(?:을|를)\s*사랑", "loves"),
		(r"([가-힣]{2,6})(?:은|는|이|가)?[^.\n]{0,20}([가-힣]{2,6})(?:을|를)\s*증오", "hates"),
		(r"([가-힣]{2,6})(?:은|는|이|가)?[^.\n]{0,20}([가-힣]{2,6})(?:을|를)\s*두려워", "fears"),
		(r"([가-힣]{2,6})(?:은|는|이|가)?[^.\n]{0,20}([가-힣]{2,6})(?:을|를)\s*신뢰", "trusts"),
		(r"([가-힣]{2,6})(?:은|는|이|가)?[^.\n]{0,20}([가-힣]{2,6})(?:을|를)\s*배신", "betrays"),
		(r"([가-힣]{2,6})(?:은|는|이|가)?[^.\n]{0,20}([가-힣]{2,6})(?:을|를)\s*보호", "protects"),
		(r"([가-힣]{2,6})(?:이|가)?\s*([가-힣]{2,6})에\s*(?:살고|거주)", "lives_in"),
		(r"([가-힣]{2,6})(?:은|는|이|가)?[^.\n]{0,20}([가-힣]{2,6})(?:을|를)\s*미워", "hates"),
		(r"([가-힣]{2,6})(?:은|는|이|가)?[^.\n]{0,20}([가-힣]{2,6})와?\s*(?:동맹|연합)", "allies"),
	]
	for pattern, relation in patterns:
		for match in re.finditer(pattern, text):
			triples.append({
				"subject": match.group(1),
				"relation": relation,
				"object": match.group(2),
				"evidence": match.group(0),
			})
	return triples


def _extract_korean_names(text: str) -> set[str]:
	return {match.group(1) for match in re.finditer(r"\b([가-힣]{2,6})(?:는|은|이|가)\b", text)}


def _build_kg_reasoning_issues(paragraphs: list[str], triples: list[dict[str, str]]) -> list[dict[str, object]]:
	issues: list[dict[str, object]] = []
	conflicts = {
		("loves", "hates"),
		("hates", "loves"),
		("trusts", "betrays"),
		("betrays", "trusts"),
	}
	for left in triples:
		for right in triples:
			if left is right:
				continue
			if left["subject"] != right["subject"] or left["object"] != right["object"]:
				continue
			if (left["relation"], right["relation"]) not in conflicts:
				continue
			location = "paragraph_1"
			for idx, paragraph in enumerate(paragraphs, start=1):
				if left["evidence"] in paragraph or right["evidence"] in paragraph:
					location = f"paragraph_{idx}"
					break
			issues.append({
				"issue_id": f"issue_{location}_kg_{left['relation']}_{right['relation']}",
				"issue": "Knowledge graph relation conflict",
				"type": "kg_relation_conflict",
				"location": location,
				"severity": "warning",
				"message": f"{left['subject']} has conflicting relations with {left['object']} ({left['relation']} vs {right['relation']}).",
				"evidence": [
					{"type": "kg_triple", "value": left},
					{"type": "kg_triple", "value": right},
				],
				"reasoning": [
					"Two opposite graph edges were extracted for the same subject-object pair.",
					"A minimal local patch should align relation polarity with canonical trajectory.",
				],
				"replace_hint": left["evidence"],
				"with_hint": right["evidence"],
			})
	return issues


def _pbkd_inferences_to_issues(inferences: list[dict[str, object]]) -> list[dict[str, object]]:
	"""Convert PBKDInference dicts (from PBKDReasoner) into structured auto-edit issues.

	Only contradictions are converted — consistent/ambiguous inferences are skipped.
	"""
	_DIM_LABELS = {"P": "Personality", "B": "Belief", "K": "Knowledge", "D": "Desire"}
	issues: list[dict[str, object]] = []
	for idx, inf in enumerate(inferences, start=1):
		if str(inf.get("verdict") or "") != "contradicts":
			continue
		character = str(inf.get("character") or "").strip()
		action = str(inf.get("action") or "").strip()
		chain = str(inf.get("chain") or "").strip()
		dimension = str(inf.get("dimension") or "B").upper()
		severity = str(inf.get("severity") or "minor")
		dim_label = _DIM_LABELS.get(dimension, dimension)
		issue_severity = "error" if severity == "critical" else "warning"
		issues.append({
			"issue_id": f"pbkd_{idx}_{character}",
			"issue": f"PBKD/{dim_label} contradiction",
			"type": "pbkd_conflict",
			"location": "paragraph_1",
			"severity": issue_severity,
			"message": chain,
			"evidence": [
				{"type": "pbkd_inference", "value": f"{character}: {action}"},
				{"type": "pbkd_chain", "value": chain},
			],
			"reasoning": [
				chain,
				f"{character}의 {dim_label}이/가 '{action}' 행동과 직접 모순됩니다.",
				f"씬을 수정하여 {character}의 {dim_label} 프로파일과 일치하도록 만드세요.",
			],
			"replace_hint": action,
			"with_hint": f"{character}의 {dim_label.lower()}과 일치하는 행동",
			"pbkd_character": character,
			"pbkd_dimension": dimension,
			"pbkd_chain": chain,
		})
	return issues


def _kg_conflicts_to_issues(conflicts: list[dict[str, object]]) -> list[dict[str, object]]:
	"""Convert KG conflict dicts (from NarrativeKnowledgeGraph.detect_scene_contradictions) to auto-edit issues."""
	issues: list[dict[str, object]] = []
	for idx, conflict in enumerate(conflicts, start=1):
		char_a = str(conflict.get("character_a") or "").strip()
		char_b = str(conflict.get("character_b") or "").strip()
		stored_rel = str(conflict.get("stored_relation") or "").strip()
		new_event = str(conflict.get("new_event") or "").strip()
		chain = str(conflict.get("chain") or "").strip()
		severity = str(conflict.get("severity") or "minor")
		weight = int(conflict.get("weight") or 1)

		issue_severity = "error" if severity == "critical" else "warning"
		issues.append({
			"issue_id": f"kg_{idx}_{char_a}_{char_b}",
			"issue": f"KG relationship conflict ({stored_rel}→{new_event})",
			"type": "kg_conflict",
			"location": "paragraph_1",
			"severity": issue_severity,
			"message": chain,
			"evidence": [
				{"type": "kg_edge", "value": f"{char_a} {stored_rel} {char_b} (confirmed {weight}x)"},
				{"type": "kg_new_event", "value": f"{char_a} {new_event} {char_b}"},
			],
			"reasoning": [
				chain,
				f"{char_a}와 {char_b}의 기존 '{stored_rel}' 관계({weight}회 확립)가 '{new_event}' 이벤트와 모순됩니다.",
				f"씬을 수정하여 기존 관계 '{stored_rel}'과 일치하도록 만드세요.",
			],
			"replace_hint": new_event,
			"with_hint": f"{char_a}와 {char_b}의 '{stored_rel}' 관계와 일치하는 행동",
			"kg_character_a": char_a,
			"kg_character_b": char_b,
			"kg_stored_relation": stored_rel,
			"kg_new_event": new_event,
			"kg_chain": chain,
		})
	return issues


def _build_pbkd_recall_issues(paragraphs: list[str]) -> list[dict[str, object]]:
	"""
	역할 기반 PBKD/관계 일관성 검사.

	이전 버그: 조사를 optional로 처리 → 목적어(Target)를 주어(Actor)로 오탐
	개선: SentenceRoleParser로 Actor(이/가/은/는 필수) / Target(을/를 필수) 분리
	  - Actor → PBKD 검사 (행동이 성격·신념과 일치하는가)
	  - Actor↔Target → 관계 검사 (기존 관계와 일치하는가)
	"""
	from backend.narrative.reasoning.sentence_role_parser import (
		CharacterRelationMemory,
		ESTABLISHES_RELATIONSHIP,
		parse_all_roles,
	)

	issues: list[dict[str, object]] = []

	# 모든 단락의 문장 분리 후 역할 파싱
	all_sentences: list[tuple[int, str]] = []  # (paragraph_idx, sentence)
	for idx, paragraph in enumerate(paragraphs, start=1):
		for sent in re.split(r"(?<=[.!?])\s*", paragraph.strip()):
			if sent.strip():
				all_sentences.append((idx, sent.strip()))

	if not all_sentences:
		return []

	sentences_only = [s for _, s in all_sentences]
	roles = parse_all_roles(sentences_only)

	# 문장 순서대로 메모리를 누적 구축하며 모순 검사
	# (선행 문장만 메모리에 포함 — 미래 문장의 관계가 과거 검사에 영향을 주지 않음)
	incremental_memory = CharacterRelationMemory()

	_EVENT_LABELS = {
		"FEAR": "공포", "LOVE": "사랑", "TRUST": "신뢰",
		"LOYAL": "충성", "PROTECT": "보호", "RESCUE": "구조",
		"BETRAYAL": "배신", "MURDER": "살해", "ATTACK": "공격",
		"HARM": "상해", "DECEIVE": "기만", "HATE": "증오",
		"HELP": "도움", "FORGIVE": "용서", "SACRIFICE": "희생",
		"REVENGE": "복수", "GIVE_UP": "포기", "RECONCILE": "화해",
	}

	for i, role in enumerate(roles):
		# 관계 확립 문장: 모순 검사 없이 메모리에 기록하고 다음으로
		if role.event_type in ESTABLISHES_RELATIONSHIP and role.actor:
			incremental_memory.record(role)
			continue
		if not role.actor or not role.event_type:
			continue

		result = incremental_memory.find_contradiction(role)
		if result is None:
			continue

		est_type, actor, targets = result
		para_idx = all_sentences[i][0]
		sentence = all_sentences[i][1]

		est_label = _EVENT_LABELS.get(est_type, est_type)
		act_label = _EVENT_LABELS.get(role.event_type, role.event_type)
		target_str = f" '{role.target}'" if role.target else ""

		# 이전에 관계를 확립한 문장 찾기 (증거로 사용)
		est_evidence: list[str] = []
		for j, prev_role in enumerate(roles[:i]):
			if prev_role.actor == actor and prev_role.event_type == est_type:
				est_evidence.append(all_sentences[j][1])
				break

		issues.append({
			"issue_id": f"issue_{para_idx}_pbkd_{actor}_{role.event_type.lower()}",
			"issue": "PBKD 충돌",
			"type": "pbkd_conflict",
			"location": f"paragraph_{para_idx}",
			"severity": "warning",
			"message": (
				f"'{actor}'이(가){target_str} '{act_label}' 행동을 보이는데, "
				f"이전에 확립된 '{est_label}' 관계/상태와 모순됩니다."
			),
			"description": (
				f"Actor: {actor} / Action: {act_label} / Target: {role.target or '(불명)'}\n"
				f"이전 확립: {actor} → {est_label} → {', '.join(targets)}"
			),
			"confidence": 0.78,
			"severity_level": "major",
			"reason": (
				f"'{actor}'은(는) 이전에 '{', '.join(targets)}'에 대해 '{est_label}' 관계를 확립했습니다. "
				f"이어지는 '{act_label}' 행동은 복선 없이 이 상태와 직접 모순됩니다."
			),
			"evidence": est_evidence + [sentence],
			"suggestion": (
				f"'{actor}'의 '{act_label}' 행동 이전에 내면 갈등·동기·전환점을 묘사하거나, "
				f"기존 '{est_label}' 상태를 점진적으로 변화시키는 문장을 삽입하세요."
			),
			"replace_hint": role.action if role.action else "",
			"with_hint": "",
			"reasoning": [
				f"행위 주체(Actor): {actor} — 이/가/은/는 조사로 식별",
				f"행위 대상(Target): {role.target or '불명'} — 을/를 조사로 식별",
				f"이전 확립 관계: {actor} → {est_label} → {', '.join(targets)}",
				f"현재 행동 '{act_label}'이 '{est_label}'과 모순됨.",
			],
		})

	return issues


def _build_timeline_recall_issues(paragraphs: list[str]) -> list[dict[str, object]]:
	issues: list[dict[str, object]] = []
	dead_markers = r"(죽었다|사망했다|이미 죽은|전사했다|숨졌다|목숨을 잃|죽음을 맞|dead|died|killed)"
	alive_markers = r"(살아있|멀쩡히|돌아왔다|나타났다|걸어왔다|말했다|등장했다|alive|returned|walked in|speaks)"
	names: set[str] = set()
	for paragraph in paragraphs:
		names.update(_extract_character_names(paragraph))
		names.update(_extract_korean_names(paragraph))
	dead_by_name: dict[str, int] = {}

	for idx, paragraph in enumerate(paragraphs, start=1):
		for name in names:
			if name in paragraph and re.search(dead_markers, paragraph, flags=re.IGNORECASE):
				dead_by_name[name] = idx

	for idx, paragraph in enumerate(paragraphs, start=1):
		for name, dead_idx in dead_by_name.items():
			if idx <= dead_idx:
				continue
			if name in paragraph and re.search(alive_markers, paragraph, flags=re.IGNORECASE):
				issues.append({
					"issue_id": f"issue_{idx}_timeline_{name}",
					"issue": "타임라인 모순",
					"type": "timeline_conflict",
					"location": f"paragraph_{idx}",
					"severity": "warning",
					"message": f"{name}이(가) 사망 확정 이후 타임라인 연결 없이 생존 상태로 등장함.",
					"evidence": [
						{"type": "timeline_state", "value": f"{name}은(는) {dead_idx}번째 단락에서 사망으로 기록됨"},
						{"type": "paragraph_excerpt", "value": paragraph[:220]},
					],
					"reasoning": [
						"명시적인 부활/플래시백 프레이밍 없이 인물의 생사 상태가 변경됨.",
						"연대기 또는 장면 프레이밍에 대한 명확화 패치가 필요함.",
					],
					"replace_hint": "살아서 나타났다",
					"with_hint": "기억 속에서, 혹은 회상으로",
				})
	return issues


def _build_canon_recall_issues(paragraphs: list[str], preserve_canon: bool) -> list[dict[str, object]]:
	if not preserve_canon:
		return []
	issues: list[dict[str, object]] = []
	forbidden_markers = r"(forbidden|금지|cannot|절대\s*할\s*수\s*없|규율상\s*금지)"
	violation_markers = r"(did anyway|강행|행했다|without consequence|아무런 대가 없이)"
	rule_paragraphs: list[tuple[int, str]] = []
	for idx, paragraph in enumerate(paragraphs, start=1):
		if re.search(forbidden_markers, paragraph, flags=re.IGNORECASE):
			rule_paragraphs.append((idx, paragraph))

	for idx, paragraph in enumerate(paragraphs, start=1):
		for rule_idx, rule_text in rule_paragraphs:
			if idx <= rule_idx:
				continue
			if re.search(violation_markers, paragraph, flags=re.IGNORECASE):
				issues.append({
					"issue_id": f"issue_{idx}_canon_rule_{rule_idx}",
					"issue": "정전 규칙 위반",
					"type": "canon_conflict",
					"location": f"paragraph_{idx}",
					"severity": "warning",
					"message": "장면이 이전에 명시된 정전 금지 사항을 위반함.",
					"evidence": [
						{"type": "canon_rule", "value": rule_text[:220]},
						{"type": "paragraph_excerpt", "value": paragraph[:220]},
					],
					"reasoning": [
						"이전 단락에서 명시적 금지 사항이 확립됨.",
						"이후 단락에서 연결/재정의 맥락 없이 직접적인 위반이 발생함.",
					],
					"replace_hint": "아무런 대가 없이",
					"with_hint": "심각한 결과를 감수하며",
				})
	return issues


def _verifier_issues(request: StructuredAutoEditRequest) -> list[dict[str, object]]:
	from backend.api.routes.consistency import _check_for_simple_conflicts

	paragraphs = _split_paragraphs(request.source_text)
	kg_triples = _extract_knowledge_graph_evidence(request.source_text) if request.use_knowledge_graph_evidence else []
	issues: list[dict[str, object]] = []

	for idx, paragraph in enumerate(paragraphs, start=1):
		lowered = paragraph.lower()
		local_evidence = [
			{"type": "paragraph_excerpt", "value": paragraph[:220]},
		]
		for triple in kg_triples:
			if triple["subject"].lower() in lowered or triple["object"].lower() in lowered:
				local_evidence.append({"type": "kg_triple", "value": triple})
		# 한국어 절대 모순: 항상/절대/결코 동시 사용
		if re.search(r"항상|언제나|늘|반드시", paragraph) and re.search(r"절대|결코|한 번도|전혀", paragraph):
			issues.append({
				"issue_id": f"issue_{idx}_logic",
				"issue": "절대적 모순",
				"type": "logic_conflict",
				"location": f"paragraph_{idx}",
				"severity": "warning",
				"message": "같은 단락에 절대 긍정('항상/언제나')과 절대 부정('절대/결코')이 동시에 사용됨.",
				"evidence": local_evidence,
				"reasoning": [
					"단일 맥락 내에서 서로 모순되는 절대 표현이 감지됨.",
					"어휘 교체를 통해 문체를 유지하면서 모순을 해소할 수 있음.",
				],
				"replace_hint": "항상",
				"with_hint": "종종",
			})
		# 한국어 부활 패턴
		if request.preserve_canon and re.search(r"부활|되살아|살아돌아|다시 살아|죽었다가\s*살|back to life|resurrect", paragraph):
			issues.append({
				"issue_id": f"issue_{idx}_canon",
				"issue": "정전 충돌",
				"type": "canon_conflict",
				"location": f"paragraph_{idx}",
				"severity": "warning",
				"message": "정전 보존이 활성화된 상태에서 부활 관련 표현이 감지됨.",
				"evidence": local_evidence,
				"reasoning": [
					"정전 보존이 활성화된 상태에서 부활 유사 표현이 감지됨.",
					"전체 재작성보다 재해석 패치를 선호하세요.",
				],
				"replace_hint": "되살아났다",
				"with_hint": "기억 속에 살아있었다",
			})

	if request.pbkd_inferences:
		issues.extend(_pbkd_inferences_to_issues(request.pbkd_inferences))
	else:
		issues.extend(_build_pbkd_recall_issues(paragraphs))

	if request.kg_conflicts:
		issues.extend(_kg_conflicts_to_issues(request.kg_conflicts))

	issues.extend(_build_canon_recall_issues(paragraphs, preserve_canon=request.preserve_canon))
	issues.extend(_build_timeline_recall_issues(paragraphs))
	if request.use_knowledge_graph_evidence:
		issues.extend(_build_kg_reasoning_issues(paragraphs, kg_triples))

	baseline = _check_for_simple_conflicts(request.source_text, [])
	for baseline_index, conflict in enumerate(baseline, start=1):
		issues.append({
			"issue_id": f"issue_baseline_{baseline_index}",
			"issue": "Consistency warning",
			"type": conflict.code,
			"location": "paragraph_1",
			"severity": str(conflict.severity.value),
			"message": conflict.message,
			"evidence": [{"type": "baseline_rule", "value": conflict.message}],
			"reasoning": ["기본 일관성 검사에서 경고가 발생했습니다."],
			"replace_hint": "",
			"with_hint": "",
		})

	# Layer 2: 문체 분석 (결정론적 — LLM 없이)
	from backend.narrative.style_analyzer import StyleAnalyzer  # noqa: PLC0415
	style_issues = StyleAnalyzer().analyze(request.source_text, provider=None, use_llm=False)
	issues.extend(style_issues)

	seen: set[tuple[str, str]] = set()
	deduped: list[dict[str, object]] = []
	for item in issues:
		key = (str(item.get("issue")), str(item.get("location")))
		if key in seen:
			continue
		seen.add(key)
		deduped.append(item)
	# consistency 이슈 우선, style 이슈 후순위 (consistency가 있으면 먼저 패치)
	consistency_first = [i for i in deduped if not str(i.get("issue_id", "")).startswith("style_")]
	style_only = [i for i in deduped if str(i.get("issue_id", "")).startswith("style_")]
	return (consistency_first + style_only)[:request.max_issues]


def _extract_character_names(text: str) -> set[str]:
	english = {match.group(0) for match in re.finditer(r"\b[A-Z][a-z]+\b", text)}
	korean = {match.group(0) for match in re.finditer(r"\b[가-힣]{2,6}\b", text)}
	return english.union(korean)


def _find_issue(issues: list[dict[str, object]], issue_type: str, location: str) -> bool:
	for issue in issues:
		if str(issue.get("type")) == issue_type and str(issue.get("location")) == location:
			return True
	return False


def _score_patch_candidate(
	request: StructuredAutoEditRequest,
	issue: dict[str, object],
	patch: dict[str, str],
	baseline_issue_count: int,
) -> dict[str, object]:
	patched_text, applied = _apply_structured_patches(request.source_text, [patch])
	applied_ok = bool(applied and applied[0].get("applied"))
	if not applied_ok:
		return {
			"total": 0.0,
			"consistency": 0.0,
			"canon": 0.0,
			"pbkd": 0.0,
			"style": 0.0,
			"reverification": {
				"accepted": False,
				"reason": applied[0].get("reason") if applied else "Patch could not be applied.",
				"issues_after": [],
			},
		}

	# For re-verification, clear pbkd_inferences: PBKD is scored independently below,
	# and re-running the same inferences/conflicts on the patched text creates phantom issues.
	verify_request = request.model_copy(update={
		"source_text": patched_text,
		"max_issues": max(12, request.max_issues),
		"pbkd_inferences": [],
		"kg_conflicts": [],
	})
	issues_after = _verifier_issues(verify_request)
	issue_type = str(issue.get("type") or "")
	issue_location = str(issue.get("location") or "")
	resolved_target = not _find_issue(issues_after, issue_type=issue_type, location=issue_location)
	new_issue_delta = max(0, len(issues_after) - max(0, baseline_issue_count - 1))

	consistency_score = 1.0 if resolved_target else 0.25
	if new_issue_delta > 0:
		consistency_score = max(0.0, consistency_score - (0.2 * new_issue_delta))

	if request.preserve_canon:
		canon_conflicts = sum(1 for item in issues_after if str(item.get("type")) == "canon_conflict")
		canon_score = 1.0 if canon_conflicts == 0 else max(0.0, 1.0 - (0.4 * canon_conflicts))
	else:
		canon_score = 1.0

	issue_type = str(issue.get("type") or "")
	if issue_type == "pbkd_conflict" and issue.get("pbkd_chain"):
		# PBKD-grounded score: check if the contradiction was resolved.
		replace_hint = str(issue.get("replace_hint") or "").strip().lower()
		contradiction_remains = replace_hint and replace_hint in patched_text.lower()
		new_pbkd_issues = sum(1 for item in issues_after if str(item.get("type")) == "pbkd_conflict")
		if contradiction_remains:
			pbkd_score = 0.0
		elif new_pbkd_issues == 0:
			pbkd_score = 1.0
		else:
			pbkd_score = round(max(0.0, 1.0 - (0.3 * new_pbkd_issues)), 3)
	elif issue_type == "kg_conflict" and issue.get("kg_chain"):
		# KG-grounded score: check if the conflicting event phrase was removed.
		replace_hint = str(issue.get("replace_hint") or "").strip().lower()
		kg_conflict_remains = replace_hint and replace_hint in patched_text.lower()
		new_kg_issues = sum(1 for item in issues_after if str(item.get("type")) == "kg_conflict")
		if kg_conflict_remains:
			pbkd_score = 0.0
		elif new_kg_issues == 0:
			pbkd_score = 1.0
		else:
			pbkd_score = round(max(0.0, 1.0 - (0.3 * new_kg_issues)), 3)
	else:
		original_names = _extract_character_names(request.source_text)
		patched_names = _extract_character_names(patched_text)
		if request.preserve_characters and original_names:
			retained = len(original_names.intersection(patched_names)) / max(1, len(original_names))
			pbkd_score = round(retained, 3)
		else:
			pbkd_score = 1.0

	style_delta = abs(len(patched_text) - len(request.source_text)) / max(1, len(request.source_text))
	style_score = max(0.0, 1.0 - min(1.0, style_delta * 4.0))

	total = round((0.35 * consistency_score) + (0.25 * canon_score) + (0.2 * pbkd_score) + (0.2 * style_score), 4)
	accepted = resolved_target and (new_issue_delta == 0 or not request.strict_reverification)
	if issue_type == "pbkd_conflict":
		pbkd_score_reason = (
			"PBKD contradiction resolved" if pbkd_score >= 1.0 else
			"PBKD contradiction still present" if pbkd_score == 0.0 else
			f"PBKD partial ({pbkd_score:.2f})"
		)
	elif issue_type == "kg_conflict":
		pbkd_score_reason = (
			"KG conflict resolved" if pbkd_score >= 1.0 else
			"KG conflict still present" if pbkd_score == 0.0 else
			f"KG partial ({pbkd_score:.2f})"
		)
	else:
		pbkd_score_reason = f"retained named entities ({pbkd_score:.2f})"
	why_lines = [
		f"Consistency score={consistency_score:.2f} (resolved_target={resolved_target}).",
		f"Canon score={canon_score:.2f}.",
		f"PBKD score={pbkd_score:.2f} — {pbkd_score_reason}.",
		f"Style score={style_score:.2f} from minimal length drift.",
	]
	if not accepted:
		why_lines.append(f"Rejected by re-verification: new_issue_delta={new_issue_delta}.")

	return {
		"total": total,
		"consistency": round(consistency_score, 4),
		"canon": round(canon_score, 4),
		"pbkd": round(pbkd_score, 4),
		"style": round(style_score, 4),
		"reverification": {
			"accepted": accepted,
			"reason": "Re-verification passed." if accepted else "Re-verification failed.",
			"issues_after": issues_after,
			"new_issue_delta": new_issue_delta,
			"resolved_target": resolved_target,
		},
		"why_this_patch": " ".join(why_lines),
	}


def _parse_patch_candidate_payload(content: str) -> list[dict[str, str]]:
	parsed = _parse_structured_patch_payload(content)
	patches = parsed.get("patches") if isinstance(parsed.get("patches"), list) else []
	results: list[dict[str, str]] = []
	for patch in patches:
		if not isinstance(patch, dict):
			continue
		results.append({
			"replace": str(patch.get("replace") or ""),
			"with": str(patch.get("with") or ""),
			"rationale": str(patch.get("rationale") or "").strip(),
		})
	return results


def _fallback_patch_candidates(issue: dict[str, object], count: int) -> list[dict[str, str]]:
	replace_hint = str(issue.get("replace_hint") or "")
	with_hint = str(issue.get("with_hint") or "")
	if not replace_hint:
		return []
	variants = [with_hint, f"{with_hint} (점진적으로)", f"{with_hint} (암묵적으로)"]
	results: list[dict[str, str]] = []
	for idx, candidate in enumerate(variants[:max(1, count)], start=1):
		results.append({
			"replace": replace_hint,
			"with": candidate,
			"rationale": f"폴백 후보 {idx}: {issue.get('issue', '문제')}",
		})
	return results


def _parse_structured_patch_payload(content: str) -> dict[str, object]:
	candidate = content.strip()
	fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", candidate, re.DOTALL | re.IGNORECASE)
	if fenced:
		candidate = fenced.group(1).strip()
	else:
		json_start = candidate.find("{")
		json_end = candidate.rfind("}")
		if 0 <= json_start < json_end:
			candidate = candidate[json_start:json_end + 1]

	try:
		payload = json.loads(candidate)
		if not isinstance(payload, dict):
			raise ValueError("Patch payload is not an object")
		raw_patches = payload.get("patches") or []
		if not isinstance(raw_patches, list):
			raw_patches = []
		patches: list[dict[str, str]] = []
		for item in raw_patches:
			if not isinstance(item, dict):
				continue
			parsed = StructuredPatch.model_validate(item)
			patches.append({
				"issue": parsed.issue,
				"location": parsed.location,
				"replace": parsed.replace,
				"with": parsed.with_text,
				"rationale": str(parsed.rationale or "").strip(),
			})
		return {
			"summary": str(payload.get("summary") or "").strip(),
			"risk_notes": _as_string_list(payload.get("risk_notes")),
			"patches": patches,
		}
	except Exception:
		return {
			"summary": "Model returned invalid patch JSON.",
			"risk_notes": ["Invalid JSON payload from model."],
			"patches": [],
		}


def _apply_structured_patches(source_text: str, patches: list[dict[str, str]]) -> tuple[str, list[dict[str, object]]]:
	paragraphs = _split_paragraphs(source_text)
	if not paragraphs:
		return source_text, []

	applied: list[dict[str, object]] = []
	for patch in patches:
		location = str(patch.get("location") or "")
		match = re.match(r"^paragraph_(\d+)$", location)
		if not match:
			applied.append({
				"patch": patch,
				"applied": False,
				"reason": "Invalid location format; expected paragraph_N.",
			})
			continue

		index = int(match.group(1)) - 1
		if index < 0 or index >= len(paragraphs):
			applied.append({
				"patch": patch,
				"applied": False,
				"reason": "Location out of range.",
			})
			continue

		replace_text = str(patch.get("replace") or "")
		with_text = str(patch.get("with") or "")
		paragraph = paragraphs[index]

		if not replace_text:
			applied.append({
				"patch": patch,
				"applied": False,
				"reason": "Patch replace text is empty.",
			})
			continue

		if replace_text not in paragraph:
			applied.append({
				"patch": patch,
				"applied": False,
				"reason": "Replace text not found in target paragraph.",
			})
			continue

		paragraphs[index] = paragraph.replace(replace_text, with_text, 1)
		applied.append({
			"patch": patch,
			"applied": True,
			"reason": "ok",
		})

	return "\n\n".join(paragraphs), applied


def get_state_engine(db: Session = Depends(get_db)) -> NarrativeStateMutationEngine:
	from backend.llm.providers import create_llm_provider
	try:
		llm_provider = create_llm_provider()
	except Exception:
		llm_provider = None
	repositories = {
		"db": db,
		"canon": CanonRepository(db),
		"character": CharacterRepository(db, commit_on_write=False),
		"lore": LoreRepository(db),
		"relationship": RelationshipRepository(db, commit_on_write=False),
		"scene": SceneRepository(db, commit_on_write=False),
		"timeline": TimelineRepository(db, commit_on_write=False),
	}
	return NarrativeStateMutationEngine(repositories, llm_provider=llm_provider)


@router.post("/state-mutation", summary="Process scene input and mutate narrative state")
def process_scene_input(
	input: SceneInput = Body(...),
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
):
	"""
	Accepts raw scene text, runs the full mutation pipeline
	(entity extraction → event generation → state mutation → persistence → consistency check)
	and returns the structured result.
	"""
	ctx = dict(input.context)
	if input.scene_title:
		ctx["scene_title"] = input.scene_title
	runtime_result = state_engine.process_scene(input.scene_text, ctx)
	return format_mutation_api_response(runtime_result)


@router.post("/version-control/branches")
def create_branch(
	request: BranchCreate,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.create_branch(request.name, from_branch=request.from_branch)


@router.get("/version-control/branches")
def list_branches(
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> list[dict[str, object]]:
	return state_engine.list_branches()


@router.post("/version-control/merge")
def merge_branch(
	request: BranchMergeRequest,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object] | None:
	return state_engine.merge_branch(request.source_branch, target_branch=request.target_branch)


@router.post("/version-control/cherry-pick")
def cherry_pick(
	request: CherryPickRequest,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object] | None:
	return state_engine.cherry_pick(request.source_branch, event_ids=request.event_ids, target_branch=request.target_branch)


@router.post("/version-control/checkout/{branch_name}")
def checkout_branch(
	branch_name: str,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object] | None:
	return state_engine.checkout_branch(branch_name)


@router.get("/version-control/snapshots")
def list_snapshots(
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> list[dict[str, object]]:
	return state_engine.list_snapshots()


@router.get("/version-control/diff")
def diff_snapshots(
	snapshot_a: str,
	snapshot_b: str,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, str]:
	return {"diff": state_engine.diff_snapshots(snapshot_a, snapshot_b)}


@router.post("/version-control/rollback")
def rollback_snapshot(
	request: SnapshotRollbackRequest,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object] | None:
	return state_engine.rollback_to_snapshot(request.snapshot_id)


@router.get("/event-sourcing/replay")
def replay_branch(
	branch: str | None = None,
	to_event_id: str | None = None,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.replay_branch(branch=branch, to_event_id=to_event_id)


@router.get("/reality/replay-determinism")
def replay_determinism(
	branch: str | None = None,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.replay_determinism(branch=branch)


@router.get("/reality/branch-verification")
def verify_branch_replay(
	branch: str | None = None,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.verify_branch_replay(branch=branch)


@router.get("/reality/snapshot-integrity/{snapshot_id}")
def verify_snapshot_integrity(
	snapshot_id: str,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.verify_snapshot_integrity(snapshot_id)


@router.post("/query")
def query_story(
	request: QueryRequest,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	if request.character_filter:
		return state_engine.retrieve_character_memories(
			query_text=request.query,
			character_name=request.character_filter,
		)
	return state_engine.query(request.query)


@router.post("/rewrite")
def rewrite_scene_text(request: RewriteRequest) -> dict[str, object]:
	from backend.llm.providers import create_llm_provider
	try:
		provider = create_llm_provider()
	except Exception as exc:
		return _fallback_rewrite_response(request, reason=str(exc))

	prompt = "\n".join([
		"다음 한국어 서사 장면을 명확성, 리듬, 작가적 통제를 위해 재작성하세요.",
		"rewritten_text, summary, suggestions, risk_notes 키를 가진 유효한 JSON만 반환하세요.",
		"명시적 지시가 없는 한 정전, 명명된 인물, 사실적 사건을 안정적으로 유지하세요.",
		f"장면 제목: {request.scene_title or '제목 없음'}",
		f"목표 어조: {request.target_tone or '균형잡힌'}",
		f"최대 길이: {request.max_length or 1200}",
		f"인물 보존: {request.preserve_characters}",
		f"정전 보존: {request.preserve_canon}",
		f"문체 메모: {', '.join(request.style_notes) if request.style_notes else '없음'}",
		f"지시사항: {request.instructions or '없음'}",
		"",
		"원본 텍스트:",
		request.source_text,
	])

	from backend.llm.providers.base import LLMMessage
	try:
		response = provider.complete([
			LLMMessage(role="system", content="당신은 한국어 소설 전문 정밀 서사 편집자입니다."),
			LLMMessage(role="user", content=prompt),
		])
		payload = _parse_rewrite_payload(response.content)
		payload.setdefault("provider_used", getattr(provider, "name", "llm"))
		payload.setdefault("reason", "")
		payload.setdefault("suggestions", [])
		payload.setdefault("risk_notes", [])
		return payload
	except Exception as exc:
		return _fallback_rewrite_response(request, reason=str(exc))


@router.post("/rewrite/structured")
def rewrite_scene_structured(request: StructuredAutoEditRequest) -> dict[str, object]:
	issues = _verifier_issues(request)
	if not issues:
		return {
			"provider_used": None,
			"summary": "Layer 1 (일관성) 및 Layer 2 (문체) 검사에서 이슈가 발견되지 않았습니다.",
			"knowledge_graph_evidence": _extract_knowledge_graph_evidence(request.source_text),
			"issues": [],
			"patches": [],
			"ranked_candidates": [],
			"selected_patches": [],
			"applied_patches": [],
			"patched_text_preview": request.source_text,
			"patched_text": request.source_text,
			"risk_notes": [],
		}

	from backend.llm.providers import create_llm_provider
	from backend.llm.providers.base import LLMMessage

	try:
		provider = create_llm_provider()
	except Exception as exc:
		provider = None
		provider_error = str(exc)
	else:
		provider_error = ""

	# Layer 2 LLM 심층 문체 분석 (provider가 있을 때만, 결정론적 분석 후 누락된 유형 추가)
	if provider is not None:
		from backend.narrative.style_analyzer import StyleAnalyzer  # noqa: PLC0415
		existing_types = {str(i.get("issue_type", i.get("type", ""))) for i in issues}
		llm_style = StyleAnalyzer().analyze(
			request.source_text, provider=provider, use_llm=True
		)
		for si in llm_style:
			if si["issue_type"] not in existing_types:
				issues.append(si)
				existing_types.add(si["issue_type"])
		# 이슈가 많으면 max_issues * 2까지 허용 (style 이슈는 경미하므로)
		max_cap = min(request.max_issues * 2, 12)
		issues = issues[:max_cap]

	kg_evidence = _extract_knowledge_graph_evidence(request.source_text) if request.use_knowledge_graph_evidence else []
	baseline_count = len(issues)
	ranked_candidates: list[dict[str, object]] = []
	selected_patches: list[dict[str, object]] = []
	risk_notes: list[str] = []
	if provider_error:
		risk_notes.append(provider_error)

	for issue_index, issue in enumerate(issues, start=1):
		issue_id = str(issue.get("issue_id") or f"issue_{issue_index}")
		issue_candidates: list[dict[str, str]] = []

		if provider is not None:
			extra_context_lines: list[str] = []
			if issue.get("pbkd_chain"):
				extra_context_lines = [
					"",
					"PBKD Reasoning Context (grounded from character profile):",
					f"  Character: {issue.get('pbkd_character', '')}",
					f"  Dimension: {issue.get('pbkd_dimension', 'B')} (Personality/Belief/Knowledge/Desire)",
					f"  Contradiction chain: {issue['pbkd_chain']}",
					f"  Problematic action: {issue.get('replace_hint', '')}",
					"  Repair goal: rewrite so the character's action aligns with their PBKD profile.",
					"  Do NOT change other characters or unrelated events.",
					"",
				]
			elif issue.get("kg_chain"):
				extra_context_lines = [
					"",
					"Knowledge Graph Context (grounded from established narrative facts):",
					f"  Character A: {issue.get('kg_character_a', '')}",
					f"  Character B: {issue.get('kg_character_b', '')}",
					f"  Established relation: {issue.get('kg_stored_relation', '')}",
					f"  Conflicting new event: {issue.get('kg_new_event', '')}",
					f"  Contradiction: {issue['kg_chain']}",
					f"  Problematic action: {issue.get('replace_hint', '')}",
					"  Repair goal: rewrite so the event aligns with the established relationship.",
					"  Do NOT change unrelated characters or events.",
					"",
				]
			prompt = "\n".join([
				"당신은 한국어 소설을 위한 서사 즉각 수정 엔진입니다.",
				"하나의 이슈에 대한 복수의 후보 패치를 생성하세요.",
				"summary, risk_notes, patches 키를 가진 엄격한 JSON만 반환하세요.",
				"각 패치에는 반드시 포함: issue, location, replace, with, rationale.",
				f"정확히 최대 {request.candidates_per_issue}개의 후보가 필요합니다.",
				"광범위한 재작성을 피하고 로컬 구간만 패치하세요.",
				*extra_context_lines,
				f"이슈: {json.dumps(issue, ensure_ascii=False)}",
				"원본 텍스트:",
				request.source_text,
			])
			try:
				response = provider.complete([
					LLMMessage(role="system", content="당신은 한국어 소설의 서사 이슈에 대해 2-3개의 결정론적 패치 대안을 생성합니다."),
					LLMMessage(role="user", content=prompt),
				])
				issue_candidates = _parse_patch_candidate_payload(response.content)
			except Exception as exc:
				risk_notes.append(f"Issue {issue_id}: {exc}")

		if not issue_candidates:
			issue_candidates = _fallback_patch_candidates(issue, request.candidates_per_issue)

		scored_list: list[dict[str, object]] = []
		for candidate_index, candidate in enumerate(issue_candidates[:request.candidates_per_issue], start=1):
			patch_id = f"{issue_id}_cand_{candidate_index}"
			patch_payload = {
				"patch_id": patch_id,
				"issue_id": issue_id,
				"issue": str(issue.get("issue") or "Issue"),
				"location": str(issue.get("location") or "paragraph_1"),
				"replace": str(candidate.get("replace") or ""),
				"with": str(candidate.get("with") or ""),
				"rationale": str(candidate.get("rationale") or "").strip(),
			}
			score = _score_patch_candidate(request=request, issue=issue, patch=patch_payload, baseline_issue_count=baseline_count)
			explainable_repair = {
				"issue": issue.get("issue"),
				"evidence": issue.get("evidence") or [],
				"reasoning": issue.get("reasoning") or [],
				"patch": {
					"replace": patch_payload["replace"],
					"with": patch_payload["with"],
				},
				"why_this_patch": score.get("why_this_patch") or "",
			}
			scored_list.append({
				**patch_payload,
				"scores": {
					"total": score["total"],
					"consistency": score["consistency"],
					"canon": score["canon"],
					"pbkd": score["pbkd"],
					"style": score["style"],
				},
				"verification": score["reverification"],
				"explainable_repair": explainable_repair,
			})

		scored_list.sort(key=lambda item: float(item.get("scores", {}).get("total", 0.0)), reverse=True)
		selected = scored_list[0] if scored_list else None
		ranked_candidates.append({
			"issue_id": issue_id,
			"issue": issue,
			"candidates": scored_list,
			"selected_patch_id": selected.get("patch_id") if isinstance(selected, dict) else None,
		})
		if isinstance(selected, dict):
			selected_patches.append(selected)

	preview_text = request.source_text
	applied_patches: list[dict[str, object]] = []
	for selected in selected_patches:
		verification = selected.get("verification") if isinstance(selected, dict) else {}
		accepted = bool(isinstance(verification, dict) and verification.get("accepted"))
		if not accepted:
			applied_patches.append({
				"patch_id": selected.get("patch_id"),
				"applied": False,
				"reason": "Patch rejected by re-verification.",
				"patch": selected,
			})
			continue

		if request.auto_apply:
			preview_text, apply_result = _apply_structured_patches(preview_text, [selected])
			applied_patches.extend(apply_result)
		else:
			applied_patches.append({
				"patch_id": selected.get("patch_id"),
				"applied": False,
				"reason": "Awaiting human review (manual mode).",
				"patch": selected,
			})

	accepted_count = sum(1 for item in selected_patches if isinstance(item.get("verification"), dict) and item["verification"].get("accepted"))
	return {
		"provider_used": getattr(provider, "name", None),
		"summary": (
			f"Layer 1+2 분석 완료 — {len(issues)}개 이슈 감지, {len(selected_patches)}개 패치 생성. "
			f"일관성: {sum(1 for i in issues if not str(i.get('issue_id','')).startswith('style_'))}개, "
			f"문체: {sum(1 for i in issues if str(i.get('issue_id','')).startswith('style_'))}개."
		),
		"knowledge_graph_evidence": kg_evidence,
		"issues": issues,
		"patches": selected_patches,
		"ranked_candidates": ranked_candidates,
		"selected_patches": selected_patches,
		"accepted_candidate_count": accepted_count,
		"applied_patches": applied_patches,
		"patched_text_preview": preview_text,
		"patched_text": preview_text if request.auto_apply else request.source_text,
		"review_required": not request.auto_apply,
		"review_endpoint": "/narrative/rewrite/structured/review",
		"risk_notes": risk_notes,
	}


@router.post("/rewrite/structured/review")
def review_structured_patches(request: StructuredPatchReviewRequest) -> dict[str, object]:
	decision_map = {item.patch_id: item for item in request.decisions}
	current_text = request.source_text
	accepted: list[dict[str, object]] = []
	rejected: list[dict[str, object]] = []
	risk_notes: list[str] = []

	seed_request = StructuredAutoEditRequest(
		source_text=current_text,
		scene_title=request.scene_title,
		instructions=request.instructions,
		target_tone=request.target_tone,
		max_length=request.max_length,
		preserve_characters=request.preserve_characters,
		preserve_canon=request.preserve_canon,
		style_notes=request.style_notes,
		strict_reverification=request.strict_reverification,
	)

	for index, raw_patch in enumerate(request.patches, start=1):
		patch_id = str(raw_patch.get("patch_id") or f"patch_{index}")
		decision = decision_map.get(patch_id)
		if decision is None:
			rejected.append({"patch_id": patch_id, "reason": "No decision provided.", "patch": raw_patch})
			continue

		if decision.action == "reject":
			rejected.append({"patch_id": patch_id, "reason": "Rejected by human.", "patch": raw_patch})
			continue

		candidate = dict(raw_patch)
		if decision.action == "edit":
			edited_with = str(decision.edited_with or "").strip()
			if not edited_with:
				rejected.append({"patch_id": patch_id, "reason": "Edit action missing edited_with text.", "patch": raw_patch})
				continue
			candidate["with"] = edited_with

		issue = {
			"type": str(candidate.get("issue_id") or candidate.get("issue") or "review_issue"),
			"location": str(candidate.get("location") or "paragraph_1"),
			"issue": str(candidate.get("issue") or "Issue"),
		}
		local_request = seed_request.model_copy(update={"source_text": current_text})
		baseline_issues = _verifier_issues(local_request)
		score = _score_patch_candidate(local_request, issue=issue, patch=candidate, baseline_issue_count=len(baseline_issues))
		verification = score.get("reverification") if isinstance(score, dict) else {}
		if isinstance(verification, dict) and verification.get("accepted"):
			current_text, apply_result = _apply_structured_patches(current_text, [candidate])
			accepted.append({
				"patch_id": patch_id,
				"decision": decision.action,
				"verification": verification,
				"apply_result": apply_result,
				"patch": candidate,
				"score": score,
			})
		else:
			rejected.append({
				"patch_id": patch_id,
				"decision": decision.action,
				"reason": "Patch failed re-verification.",
				"verification": verification,
				"patch": candidate,
			})
			risk_notes.append(f"Patch {patch_id} failed re-verification.")

	final_request = seed_request.model_copy(update={"source_text": current_text})
	final_issues = _verifier_issues(final_request)
	return {
		"summary": "Human-in-the-loop review completed.",
		"accepted_patches": accepted,
		"rejected_patches": rejected,
		"final_issue_count": len(final_issues),
		"final_issues": final_issues,
		"patched_text": current_text,
		"risk_notes": risk_notes,
	}


@router.get("/relationships/graph/{character_id}")
def relationship_graph_summary(
	character_id: str,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.relationship_summary(character_id)


@router.get("/relationships/graph")
def relationship_dimension_query(
	dimension: str,
	minimum: float = 0.5,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> list[dict[str, object]]:
	return state_engine.relationship_dimension(dimension=dimension, minimum=minimum)


@router.get("/knowledge-graph/summary")
def knowledge_graph_summary(
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.knowledge_graph_summary()


@router.get("/knowledge-graph/traverse")
def knowledge_graph_traverse(
	node_id: str,
	depth: int = 1,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.knowledge_graph_traverse(node_id=node_id, depth=depth)


@router.get("/debug/semantic-memory/histogram")
def semantic_memory_histogram(
	character_name: str | None = None,
	bucket_size: float = 0.1,
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.semantic_memory_histogram(character_name=character_name, bucket_size=bucket_size)


@router.post("/debug/semantic-memory/promotion")
def run_semantic_memory_promotion(
	state_engine: NarrativeStateMutationEngine = Depends(get_state_engine),
) -> dict[str, object]:
	return state_engine.run_semantic_promotion_job()


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, object]:
	characters = CharacterRepository(db)
	scenes = SceneRepository(db)
	timeline = TimelineRepository(db)
	lore = LoreRepository(db)
	relationships = RelationshipRepository(db)
	return {
		"characters": characters.count(),
		"scenes": scenes.count(),
		"timeline_events": timeline.count(),
		"lore_facts": lore.count(),
		"relationships": relationships.count(),
	}


@router.post("/characters", response_model=CharacterState, status_code=status.HTTP_201_CREATED)
def create_character(request: CharacterState, db: Session = Depends(get_db)) -> CharacterState:
	repo = CharacterRepository(db)
	existing = repo.get_by_name(request.name)
	if existing is not None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=f"Character with name '{request.name}' already exists (id={existing.id}). Use PATCH /characters/{existing.id} to update.",
		)
	traits, goals, metadata = _merge_pbkd_to_fields(
		traits=request.traits,
		goals=request.goals,
		metadata=request.metadata,
		pbkd=request.pbkd,
	)
	character = repo.create(
		character_id=request.id,
		name=request.name,
		role=request.role.value,
		traits=traits,
		goals=goals,
		background=request.background,
		status=request.status,
		metadata=metadata,
	)
	return CharacterState(
		id=character.id,
		name=character.name,
		role=_normalize_character_role(character.role),
		traits=character.traits,
		goals=character.goals,
		pbkd=_normalize_pbkd(character.traits, character.goals, character.metadata_json),
		background=character.background,
		status=character.status,
		metadata=character.metadata_json,
		created_at=character.created_at,
		updated_at=character.updated_at,
	)


@router.patch("/characters/{character_id}", response_model=CharacterState)
def update_character(character_id: str, request: CharacterUpdate, db: Session = Depends(get_db)) -> CharacterState:
	repo = CharacterRepository(db)
	existing = repo.get(character_id)
	if existing is None:
		existing_traits: list[str] = []
		existing_goals: list[str] = []
		existing_metadata: dict[str, object] = {}
	else:
		existing_traits = list(existing.traits)
		existing_goals = list(existing.goals)
		existing_metadata = dict(existing.metadata_json or {})

	patch = request.model_dump(exclude_unset=True)
	if "role" in patch and patch["role"] is not None:
		patch["role"] = patch["role"].value
	pbkd_update = patch.pop("pbkd", None)
	if pbkd_update is not None:
		pbkd_obj = CharacterPBKD.model_validate(pbkd_update)
		next_traits, next_goals, next_meta = _merge_pbkd_to_fields(
			traits=patch.get("traits", existing_traits),
			goals=patch.get("goals", existing_goals),
			metadata=patch.get("metadata", existing_metadata),
			pbkd=pbkd_obj,
		)
		patch["traits"] = next_traits
		patch["goals"] = next_goals
		patch["metadata"] = next_meta
	character = repo.upsert(character_id, patch)
	return CharacterState(
		id=character.id,
		name=character.name,
		role=_normalize_character_role(character.role),
		traits=character.traits,
		goals=character.goals,
		pbkd=_normalize_pbkd(character.traits, character.goals, character.metadata_json),
		background=character.background,
		status=character.status,
		metadata=character.metadata_json,
		created_at=character.created_at,
		updated_at=character.updated_at,
	)


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: str, db: Session = Depends(get_db)) -> None:
	repo = CharacterRepository(db)
	existing = repo.get(character_id)
	if existing is None:
		raise HTTPException(status_code=404, detail="Character not found")
	db.delete(existing)
	db.commit()


@router.get("/characters", response_model=list[CharacterState])
def list_characters(db: Session = Depends(get_db)) -> list[CharacterState]:
	repo = CharacterRepository(db)
	return [
		CharacterState(
			id=item.id,
			name=item.name,
			role=_normalize_character_role(item.role),
			traits=item.traits,
			goals=item.goals,
			pbkd=_normalize_pbkd(item.traits, item.goals, item.metadata_json),
			background=item.background,
			status=item.status,
			metadata=item.metadata_json,
			created_at=item.created_at,
			updated_at=item.updated_at,
		)
		for item in repo.list()
	]


@router.get("/characters/{character_id}/pbkd", response_model=CharacterPBKD)
def get_character_pbkd(character_id: str, db: Session = Depends(get_db)) -> CharacterPBKD:
	repo = CharacterRepository(db)
	item = repo.get(character_id)
	if item is None:
		return CharacterPBKD()
	return _normalize_pbkd(item.traits, item.goals, item.metadata_json)


@router.get("/characters/{character_id}/memory")
def get_character_memory(character_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
	"""Return raw memory state — trait_events with confidence + source_scene for PBKD Explorer."""
	repo = CharacterRepository(db)
	char = repo.get(character_id)
	if char is None:
		return {"character_id": character_id, "name": "", "trait_events": [], "pending_trait_events": []}
	metadata = char.metadata_json or {}
	memory = metadata.get("memory", {}) if isinstance(metadata, dict) else {}
	return {
		"character_id": character_id,
		"name": char.name,
		"trait_events": memory.get("trait_events", [])[-80:],
		"pending_trait_events": memory.get("pending_trait_events", [])[-80:],
	}


@router.get("/characters/pbkd/search")
def search_character_pbkd(
	query: str,
	scopes: str = "P,B,K,D",
	db: Session = Depends(get_db),
) -> dict[str, object]:
	repo = CharacterRepository(db)
	q = query.strip().lower()
	scope_map = {
		"P": "personality",
		"B": "beliefs",
		"K": "knowledge",
		"D": "desires",
	}
	allowed = {scope_map.get(part.strip().upper(), "") for part in scopes.split(",")}
	allowed.discard("")
	results: list[dict[str, object]] = []
	for item in repo.list():
		pbkd = _normalize_pbkd(item.traits, item.goals, item.metadata_json)
		matches: dict[str, list[str]] = {}
		if "personality" in allowed:
			values = [v for v in pbkd.personality if q in v.lower()]
			if values:
				matches["P"] = values
		if "beliefs" in allowed:
			values = [v for v in pbkd.beliefs if q in v.lower()]
			if values:
				matches["B"] = values
		if "knowledge" in allowed:
			values = [v for v in pbkd.knowledge if q in v.lower()]
			if values:
				matches["K"] = values
		if "desires" in allowed:
			values = [v for v in pbkd.desires if q in v.lower()]
			if values:
				matches["D"] = values
		if matches:
			results.append({
				"character_id": item.id,
				"name": item.name,
				"matches": matches,
			})
	return {
		"query": query,
		"scopes": [s.strip().upper() for s in scopes.split(",") if s.strip()],
		"count": len(results),
		"results": results,
	}


@router.post("/scenes", response_model=dict[str, object], status_code=status.HTTP_201_CREATED)
def create_scene(request: SceneCreate, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = SceneRepository(db)
	scene = repo.create(title=request.title, summary=request.summary, beats=request.beats, characters=request.characters)
	return {
		"id": scene.id,
		"title": scene.title,
		"summary": scene.summary,
		"beats": scene.beats,
		"characters": scene.characters,
		"created_at": scene.created_at,
	}


@router.get("/scenes")
def list_scenes(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	repo = SceneRepository(db)
	return [
		{
			"id": scene.id,
			"title": scene.title,
			"summary": scene.summary,
			"beats": scene.beats,
			"characters": scene.characters,
			"created_at": scene.created_at,
		}
		for scene in repo.list()
	]


@router.post("/world/lore")
def add_lore_fact(request: LoreFactCreate, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = LoreRepository(db)
	fact = repo.upsert(request.key, request.value, source=request.source, tags=sorted(request.tags))
	return {"key": fact.key, "value": fact.value, "source": fact.source, "tags": fact.tags}


@router.get("/world/lore")
def list_lore_facts(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	repo = LoreRepository(db)
	return [{"key": fact.key, "value": fact.value, "source": fact.source, "tags": fact.tags} for fact in repo.list()]


@router.post("/timeline/events")
def add_timeline_event(request: TimelineEventCreate, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = TimelineRepository(db)
	event = repo.create(title=request.title, description=request.description, happened_at=request.happened_at or datetime.now(UTC))
	return {
		"id": event.id,
		"title": event.title,
		"description": event.description,
		"happened_at": event.happened_at,
		"metadata": event.metadata_json,
	}


_SYSTEM_LOG_PATTERNS = [
	re.compile(r"^장면 사건이 타임라인에 기록됨$"),
	re.compile(r"^'.+' 공간이 설정됨$"),
	re.compile(r"^장면 '.+' (시작|종료)$"),
	re.compile(r"^장면이 (시작됩니다|끝난다|끝납니다|종료됨|막을 내림)$"),
]


def _classify_timeline_event(title: str | None) -> Literal["story", "system"]:
	"""Distinguish pipeline bookkeeping entries (scene/location lifecycle logs)
	from actual narrative events, so the two don't get mixed in the timeline UI."""
	text = (title or "").strip()
	for pattern in _SYSTEM_LOG_PATTERNS:
		if pattern.match(text):
			return "system"
	return "story"


@router.get("/timeline/events")
def list_timeline_events(
	kind: Literal["story", "system", "all"] = "all",
	db: Session = Depends(get_db),
) -> list[dict[str, object]]:
	repo = TimelineRepository(db)
	events = [
		{
			"id": event.id,
			"title": event.title,
			"description": event.description,
			"happened_at": event.happened_at,
			"metadata": event.metadata_json,
			"kind": _classify_timeline_event(event.title),
		}
		for event in repo.list()
	]
	if kind == "all":
		return events
	return [e for e in events if e["kind"] == kind]


@router.post("/relationships")
def add_relationship(request: RelationshipCreate, db: Session = Depends(get_db)) -> dict[str, object]:
	repo = RelationshipRepository(db)
	relationship = repo.create(
		source=request.source,
		target=request.target,
		relationship_type=request.relationship_type.value,
		strength=request.strength,
		notes=[request.note] if request.note else [],
	)
	return {
		"id": relationship.id,
		"source": relationship.source,
		"target": relationship.target,
		"relationship_type": relationship.relationship_type,
		"strength": relationship.strength,
		"notes": relationship.notes,
		"created_at": relationship.created_at,
	}
