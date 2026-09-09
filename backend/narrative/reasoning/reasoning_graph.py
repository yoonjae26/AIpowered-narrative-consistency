"""
Reasoning Graph Builder — dynamic DAG-based reasoning planner.

Replaces static if-else intent routing with a multi-intent composition engine.
Each node carries a *role* that constrains what GPT is allowed to do with that source:

  ground_truth — source result IS the answer; GPT cites and narrates, never overrides.
  motivation   — PBKD profile; GPT uses to explain the causal chain behind the answer.
  evidence     — supporting facts GPT may cite to support the ground-truth conclusion.
  hypothesis   — speculative inference allowed; GPT MUST use uncertainty language.
                 confidence < 1.0 encodes how speculative the claim is.
  constraint   — world/lore rules that invalidate any contradicting inference.

Multiple intents are detected simultaneously and composed into a single DAG.
No exclusive branches — "배신한다면 누구 편에 설 가능성이 높은가?" correctly activates
COUNTERFACTUAL + RELATIONSHIP + FUTURE all at once.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal


SourceType = Literal["KG", "PBKD", "Memory", "World"]
NodeRole = Literal["ground_truth", "motivation", "evidence", "hypothesis", "constraint"]
SupportType = Literal["explicit", "observed", "derived"]

_ROLE_LABELS: dict[str, str] = {
    "ground_truth": "★ GROUND TRUTH — 반박 금지. 반드시 인용하라.",
    "motivation":   "  동기 — Belief/Desire/Goal에서 동기를 확인하라. 해석에만 사용.",
    "evidence":     "  증거 — 지지 증거로 사용하라. 추론의 근거로 인용하라.",
    "constraint":   "⚠ 제약 — 이 규칙을 위반하는 모든 추론은 금지된다.",
    "hypothesis":   "◇ 가설 — 추론만 허용. '가능성', '가정하면' 표현 필수. 단정 금지.",
}

_ROLE_PRIORITY: dict[str, int] = {
    "ground_truth": 1,
    "motivation": 2,
    "evidence": 3,
    "constraint": 4,
    "hypothesis": 5,
}


@dataclass(slots=True)
class ReasoningNode:
    node_id: str
    source: SourceType
    role: NodeRole
    priority: int          # lower = executed first; drives topological order
    query_hint: str        # what to retrieve / reason about from this source
    confidence: float = 1.0        # < 1.0 for hypothesis nodes
    support_type: SupportType = "explicit"  # how the claim is grounded


@dataclass
class ReasoningGraph:
    question: str
    intent: str          # may be compound, e.g. "COUNTERFACTUAL+RELATIONSHIP"
    character_names: list[str]
    nodes: list[ReasoningNode] = field(default_factory=list)

    @property
    def ordered_nodes(self) -> list[ReasoningNode]:
        return sorted(self.nodes, key=lambda n: n.priority)

    def ground_truth_sources(self) -> list[SourceType]:
        return [n.source for n in self.nodes if n.role == "ground_truth"]

    def hypothesis_nodes(self) -> list[ReasoningNode]:
        return [n for n in self.nodes if n.role == "hypothesis"]

    def to_dict(self) -> dict[str, Any]:
        """Serialize graph to a JSON-compatible dict for frontend pipeline display."""
        return {
            "intent": self.intent,
            "character_names": self.character_names,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "source": n.source,
                    "role": n.role,
                    "priority": n.priority,
                    "query_hint": n.query_hint,
                    "confidence": n.confidence,
                    "support_type": n.support_type,
                }
                for n in self.ordered_nodes
            ],
        }

    def as_plan_text(self) -> str:
        """Format graph as a numbered execution plan embedded in the LLM prompt."""
        name_str = ", ".join(self.character_names) if self.character_names else "미정"
        lines: list[str] = [
            f"[추론 계획 — {self.intent}]",
            f"대상 인물: {name_str}",
            "",
        ]
        for i, node in enumerate(self.ordered_nodes, 1):
            label = _ROLE_LABELS.get(node.role, "  참고")
            conf_tag = f" (confidence={node.confidence:.2f})" if node.role == "hypothesis" else ""
            lines.append(f"Step{i} [{node.source}|{node.support_type}]: {node.query_hint}")
            lines.append(f"        {label}{conf_tag}")
        lines += [
            "",
            "★ 핵심 지시: GROUND TRUTH 항목은 GPT 판단보다 우선한다.",
            "  이를 기반으로 동기/증거/가설을 해석하라. 반박 금지.",
        ]
        return "\n".join(lines)


class ReasoningGraphBuilder:
    """Builds a reasoning dependency graph from question structure.

    Analysis is rule-based (no LLM call). Multiple intents are detected
    simultaneously and composed into a single prioritized DAG — key difference
    from a static planner that picks a single branch per question.

    Example — "카엘은 오린이 배신한다면 세라핀은 누구 편에 설 가능성이 높은가?":
      Detects: COUNTERFACTUAL + RELATIONSHIP + FUTURE (all at once)
      Builds:  KG[ground_truth] → PBKD[motivation] → Memory[evidence]
               → World[constraint] → PBKD[hypothesis, conf=0.35]
    """

    _WHO_RE = re.compile(r"누구|who")
    _WHY_RE = re.compile(r"왜|why|이유|동기|reason|motivation")
    _HOW_RE = re.compile(r"어떻게|how|방법|방식")
    _FUTURE_RE = re.compile(r"앞으로|미래|예측|앞날|향후|이후|predict|future|will")
    _CURRENT_RE = re.compile(r"지금|현재|요즘|now|current")
    _PAST_RE = re.compile(r"과거|이전|사건|history|past|happened|했었|있었")
    _TRUST_RE = re.compile(r"신뢰|믿|trust")
    _ALLIANCE_RE = re.compile(r"동맹|연합|ally|alliance")
    _ENEMY_RE = re.compile(r"적|원수|enemy|hatred|적대|싫")
    _FRIEND_RE = re.compile(r"친구|우정|friend|friendship|가까운|친한")
    _LIKELY_RE = re.compile(r"가능성|likely|아마|probably|추정|높은")
    _GOAL_RE = re.compile(r"계획|목표|바라|원하|하려|하고자|goal|plan|intend|aim")
    _COUNTERFACTUAL_RE = re.compile(
        r"만약|만일|배신|배반|한다면|된다면|했다면|가정하면"
        r"|if\s+\w+\s+(?:would|were|had)|counterfactual"
    )

    @staticmethod
    def _infer_support_type(source: str, role: str) -> SupportType:
        """Derive support_type from source + role.

        explicit  — claim is directly stated in the source (KG edge, PBKD field, World rule)
        observed  — claim records something that was witnessed / happened (Memory event)
        derived   — claim is inferred or speculated; must use uncertainty language
        """
        if role == "hypothesis":
            return "derived"
        if source == "Memory":
            return "observed"
        return "explicit"

    def build(
        self,
        question: str,
        intent: str,
        character_names: list[str],
    ) -> ReasoningGraph:
        q = question
        names = ", ".join(character_names) if character_names else "대상 인물"

        # ── Detect ALL active intents simultaneously ────────────────────────
        has_who = bool(self._WHO_RE.search(q))
        has_why = bool(self._WHY_RE.search(q)) or intent == "MOTIVATION"
        has_future = bool(self._FUTURE_RE.search(q)) or intent == "PREDICTION"
        has_past = bool(self._PAST_RE.search(q)) or intent == "HISTORY"
        has_current = bool(self._CURRENT_RE.search(q)) or intent == "NARRATIVE"
        has_likely = bool(self._LIKELY_RE.search(q))
        has_goal = bool(self._GOAL_RE.search(q))
        has_counterfactual = bool(self._COUNTERFACTUAL_RE.search(q))
        is_trust = bool(self._TRUST_RE.search(q))
        is_alliance = bool(self._ALLIANCE_RE.search(q))
        is_enemy = bool(self._ENEMY_RE.search(q))
        is_friend = bool(self._FRIEND_RE.search(q))
        has_rel_kw = is_trust or is_alliance or is_enemy or is_friend

        intents: set[str] = set()
        if intent == "RELATIONSHIP" or (has_who and has_rel_kw):
            intents.add("RELATIONSHIP")
        if has_why:
            intents.add("WHY")
        if has_future or (has_likely and not has_rel_kw):
            intents.add("FUTURE")
        if has_past:
            intents.add("PAST")
        if has_current:
            intents.add("CURRENT")
        if has_counterfactual:
            intents.add("COUNTERFACTUAL")
        if not intents:
            intents.add("FALLBACK")

        has_relationship = "RELATIONSHIP" in intents
        has_motivation = "WHY" in intents
        has_speculative = "FUTURE" in intents or "COUNTERFACTUAL" in intents

        rel_dim = (
            "trust" if is_trust else
            "alliance" if is_alliance else
            "hatred" if is_enemy else
            "friendship" if is_friend else
            "general"
        )

        # ── Compose raw nodes from all detected intents ─────────────────────
        # (node_id, source, role, query_hint, confidence)
        raw: list[tuple[str, str, str, str, float]] = []

        # RELATIONSHIP → KG is ground truth
        if has_relationship:
            raw.append((
                "kg_rel", "KG", "ground_truth",
                f"{names}의 {rel_dim} dimension 엣지를 조회하라. "
                "가장 높은 score의 인물이 정답이다.",
                1.0,
            ))

        # MOTIVATION → PBKD explains why; always motivation role
        # (GT status is assigned by the promotion pass if nothing else claims it)
        if has_motivation:
            raw.append((
                "pbkd_motive", "PBKD", "motivation",
                f"{names}의 Belief, Desire, Goal에서 동기를 확인하라.",
                1.0,
            ))
        elif has_relationship:
            raw.append((
                "pbkd_exp", "PBKD", "motivation",
                f"{names}의 Belief/Desire에서 이 관계를 선택한 이유를 해석하라.",
                1.0,
            ))
        elif has_goal:
            # Query mentions planning/goals (계획/목표) but no explicit WHY — pull PBKD
            # Goal/Desire to contextualize the action (do not override Memory GT).
            raw.append((
                "pbkd_goal", "PBKD", "motivation",
                f"{names}의 Goal/Desire에서 현재 행동의 목표와 계획을 확인하라.",
                1.0,
            ))

        # MEMORY — role and content depend on temporal focus
        # Becomes ground_truth only when no KG/PBKD is already claiming it
        other_gt = has_relationship  # KG will be GT; memory demoted to evidence
        if has_past:
            raw.append((
                "mem_events", "Memory",
                "evidence" if other_gt or has_motivation else "ground_truth",
                f"{names}와 관련된 event를 시간순으로 정리하라.",
                1.0,
            ))
        elif has_current:
            raw.append((
                "mem_current", "Memory",
                "evidence" if other_gt else "ground_truth",
                f"{names}의 현재 scene/상태를 파악하라.",
                1.0,
            ))
        elif has_speculative:
            raw.append((
                "mem_now", "Memory",
                "evidence" if other_gt or has_motivation else "ground_truth",
                f"{names}의 현재 상태를 파악하라 (추측 금지, 사실만).",
                1.0,
            ))
        else:
            raw.append((
                "mem_ctx", "Memory", "evidence",
                f"{names}와 관련된 최근 scene/event에서 맥락을 파악하라.",
                1.0,
            ))

        # WORLD CONSTRAINT — limits speculative reasoning
        if has_speculative:
            raw.append((
                "world_const", "World", "constraint",
                "Lore/WorldState에서 예측/가정을 제한하는 세계 규칙을 확인하라. "
                "제약 위반 추론은 전면 금지.",
                1.0,
            ))

        # HYPOTHESIS node — GPT's speculative output, explicitly bounded
        if "COUNTERFACTUAL" in intents:
            raw.append((
                "cf_hypothesis", "PBKD", "hypothesis",
                f"'가정 시나리오' 하에서 {names}의 행동 방향을 추론하라. "
                "'가능성이 있다', '가정하면', '추론하면' 표현 필수. 단정 금지.",
                0.35,
            ))
        elif "FUTURE" in intents:
            raw.append((
                "future_hypothesis", "PBKD", "hypothesis",
                f"{names}의 Goal/Desire에서 앞으로의 행동 방향을 추론하라. "
                "'가능성이 있다' 표현 필수.",
                0.50,
            ))

        # FALLBACK — when no intent matched
        if not raw:
            raw = [
                ("kg_any", "KG", "ground_truth", f"{names}의 모든 KG 관계를 확인하라.", 1.0),
                ("mem_any", "Memory", "evidence", f"{names}와 관련된 Memory를 확인하라.", 1.0),
                ("pbkd_any", "PBKD", "motivation", f"{names}의 PBKD를 확인하라.", 1.0),
            ]

        # ── Promote: if nothing is ground_truth, elevate the first eligible node ─
        if not any(role == "ground_truth" for _, _, role, _, _ in raw):
            for i, (nid, src, role, hint, conf) in enumerate(raw):
                if role not in ("hypothesis", "constraint"):
                    raw[i] = (nid, src, "ground_truth", hint, conf)
                    break

        # ── Deduplicate by node_id, sort by role priority, assign final priorities ─
        seen: set[str] = set()
        unique: list[tuple[str, str, str, str, float]] = []
        for item in raw:
            if item[0] not in seen:
                seen.add(item[0])
                unique.append(item)

        unique.sort(key=lambda x: _ROLE_PRIORITY.get(x[2], 3))

        graph_nodes = [
            ReasoningNode(
                node_id=node_id,
                source=source,      # type: ignore[arg-type]
                role=role,          # type: ignore[arg-type]
                priority=i,
                query_hint=hint,
                confidence=conf,
                support_type=self._infer_support_type(source, role),
            )
            for i, (node_id, source, role, hint, conf) in enumerate(unique, 1)
        ]

        intent_label = (
            "+".join(sorted(intents)) if len(intents) > 1 else next(iter(intents))
        )
        return ReasoningGraph(
            question=question,
            intent=intent_label,
            character_names=character_names,
            nodes=graph_nodes,
        )
