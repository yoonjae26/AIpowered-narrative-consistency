"""
Symbolic Semantic Consistency Engine

Pipeline:
  Narrative
    ↓
  Claim Extraction  →  (subject, predicate, object)
    ↓
  KG Relation Lookup  →  character pairs × relationship_type
    ↓
  PBKD Lookup  →  beliefs, personality per character
    ↓
  Conflict Ontology  →  compatible / incompatible action vocabulary
    ↓
  Conflict Score  →  Issues
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.database.models.character import Character
from backend.database.models.relationship import Relationship


# ── Conflict Ontology ─────────────────────────────────────────────────────────

# Korean action vocabulary by semantic category
COOPERATIVE_VERBS = [
    "협력", "동맹", "돕", "함께", "신뢰", "믿", "지원", "협조", "공조",
    "합력", "합심", "연합", "제휴", "협심", "우정", "친구", "동행",
]
HOSTILE_VERBS = [
    "적대", "배신", "공격", "싸움", "싸우", "살해", "증오", "혐오",
    "배반", "반역", "대적", "살인", "적군", "원수", "죽이", "전투",
]
ROMANTIC_VERBS = ["사랑", "연인", "결혼", "연모", "좋아", "짝사랑"]
RIVAL_VERBS = ["경쟁", "라이벌", "다투", "겨루", "대결"]
RESURRECTION_TOKENS = ["부활", "되살아", "소생", "환생", "살아났"]

# relationship_type → action verbs that CONTRADICT it
_REL_CONFLICT_MAP: dict[str, list[str]] = {
    "ally":     HOSTILE_VERBS,
    "family":   HOSTILE_VERBS,
    "romantic": HOSTILE_VERBS,
    "mentor":   HOSTILE_VERBS,
    "enemy":    COOPERATIVE_VERBS + ROMANTIC_VERBS,
    "rival":    COOPERATIVE_VERBS + ROMANTIC_VERBS,
}

# (pbkd_trigger_keywords, conflicting_action_verbs, rule_label)
_PBKD_CONFLICT_MAP: list[tuple[list[str], list[str], str]] = [
    (["평화", "비폭력", "평화주의"],  HOSTILE_VERBS,                          "평화주의 신념"),
    (["충성", "충실", "헌신"],         ["배신", "배반", "반역", "裏切"],        "충성 신념"),
    (["정직", "진실", "성실"],         ["거짓", "속임", "기만", "거짓말"],       "정직 신념"),
    (["보호", "수호", "지킴"],         ["배신", "배반", "공격", "살해"],         "수호 신념"),
    (["약자", "정의"],                 ["공격", "살해", "증오"],                 "정의 신념"),
]


@dataclass
class SymbolicIssue:
    severity: str   # "error" | "warning" | "info"
    code: str
    message: str
    entities: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    rule: str = ""


@dataclass
class _Mention:
    name: str
    character_id: str
    sentences: list[str] = field(default_factory=list)


class SymbolicConsistencyEngine:
    def __init__(
        self,
        characters: list[Character],
        relationships: list[Relationship],
    ) -> None:
        self._chars: dict[str, Character] = {c.id: c for c in characters}
        self._rels: list[Relationship] = relationships

    def check(self, narrative: str) -> list[SymbolicIssue]:
        sentences = _split_sentences(narrative)
        mentions = self._extract_mentions(sentences)
        mention_ids = {m.character_id for m in mentions}

        issues: list[SymbolicIssue] = []
        issues.extend(self._r1_dead_characters(mentions, narrative))
        issues.extend(self._r2_relationship_conflicts(mention_ids, mentions, sentences))
        issues.extend(self._r3_pbkd_conflicts(mentions))
        return issues

    # ── Claim Extraction ──────────────────────────────────────────────────────

    def _extract_mentions(self, sentences: list[str]) -> list[_Mention]:
        result: list[_Mention] = []
        for char_id, char in self._chars.items():
            matched = [s for s in sentences if char.name in s]
            if matched:
                result.append(_Mention(
                    name=char.name,
                    character_id=char_id,
                    sentences=matched,
                ))
        return result

    # ── R1: Dead character appears ────────────────────────────────────────────

    def _r1_dead_characters(
        self, mentions: list[_Mention], narrative: str
    ) -> list[SymbolicIssue]:
        if any(tok in narrative for tok in RESURRECTION_TOKENS):
            return []
        issues: list[SymbolicIssue] = []
        for mention in mentions:
            char = self._chars[mention.character_id]
            if (char.status or "").lower() == "dead":
                issues.append(SymbolicIssue(
                    severity="error",
                    code="dead_character_active",
                    message=(
                        f"'{char.name}'은(는) 사망 상태이지만 "
                        f"내러티브에 활동 중인 인물로 등장합니다."
                    ),
                    entities=[char.name],
                    evidence=mention.sentences[:2],
                    rule="R1",
                ))
        return issues

    # ── R2: Relationship conflict ─────────────────────────────────────────────

    def _r2_relationship_conflicts(
        self,
        mention_ids: set[str],
        mentions: list[_Mention],
        sentences: list[str],
    ) -> list[SymbolicIssue]:
        issues: list[SymbolicIssue] = []
        mention_map = {m.character_id: m for m in mentions}

        for rel in self._rels:
            if rel.source not in mention_ids or rel.target not in mention_ids:
                continue
            char_a = self._chars.get(rel.source)
            char_b = self._chars.get(rel.target)
            if not char_a or not char_b:
                continue

            # Prefer sentences that name both characters; fall back to all
            both = [
                s for s in sentences
                if char_a.name in s and char_b.name in s
            ]
            context = " ".join(both or [
                s for s in (
                    mention_map.get(rel.source, _Mention("", "", [])).sentences
                    + mention_map.get(rel.target, _Mention("", "", [])).sentences
                )
            ])

            conflict_verbs = _REL_CONFLICT_MAP.get(rel.relationship_type, [])
            found = _verbs_in(context, conflict_verbs)
            if not found:
                continue

            severity = "error" if rel.strength >= 0.7 else "warning"
            issues.append(SymbolicIssue(
                severity=severity,
                code="relationship_conflict",
                message=(
                    f"'{char_a.name}'와(과) '{char_b.name}'은(는) "
                    f"'{rel.relationship_type}' 관계이지만 "
                    f"상충하는 행동({', '.join(found)})이 묘사됩니다."
                ),
                entities=[char_a.name, char_b.name],
                evidence=(both or [])[:2] + [
                    f"저장된 관계: {rel.relationship_type} (강도 {rel.strength:.1f})"
                ],
                rule="R2",
            ))
        return issues

    # ── R3: PBKD conflict ─────────────────────────────────────────────────────

    def _r3_pbkd_conflicts(self, mentions: list[_Mention]) -> list[SymbolicIssue]:
        issues: list[SymbolicIssue] = []
        for mention in mentions:
            char = self._chars[mention.character_id]
            meta = char.metadata_json or {}

            pbkd_text = " ".join([
                " ".join(char.traits or []),
                " ".join(str(x) for x in (meta.get("beliefs") or [])),
                " ".join(str(x) for x in (meta.get("personality") or [])),
                " ".join(str(x) for x in (char.goals or [])),
            ]).lower()

            if not pbkd_text.strip():
                continue

            context = " ".join(mention.sentences)
            for trigger_kws, conflict_verbs, rule_label in _PBKD_CONFLICT_MAP:
                if not any(kw in pbkd_text for kw in trigger_kws):
                    continue
                found = _verbs_in(context, conflict_verbs)
                if not found:
                    continue
                issues.append(SymbolicIssue(
                    severity="warning",
                    code="pbkd_conflict",
                    message=(
                        f"'{char.name}'은(는) {rule_label}을(를) 가지고 있지만 "
                        f"이와 상충하는 행동({', '.join(found)})이 묘사됩니다."
                    ),
                    entities=[char.name],
                    evidence=mention.sentences[:2],
                    rule="R3",
                ))
                break  # one PBKD issue per character per run
        return issues


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。.!?！？\n]+", text)
    return [p.strip() for p in parts if p.strip()]


def _verbs_in(text: str, verbs: list[str]) -> list[str]:
    return [v for v in verbs if v in text]
