"""
PBKD Reasoning Layer — inferential bridge between character profile and scene events.

Reads author-defined PBKD from character.metadata_json["pbkd"] and reasons
whether each character's actions in the scene are consistent with their profile.

Unlike keyword search (RAG), this produces inference chains:
  "카엘의 belief '복수는 정의가 아니다'는 이 씬에서의 배신 행동과 모순됩니다."
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.llm.providers.base import BaseLLMProvider, LLMMessage

logger = logging.getLogger(__name__)

_VERDICT_CONSISTENT = "consistent"
_VERDICT_CONTRADICTS = "contradicts"
_VERDICT_AMBIGUOUS = "ambiguous"

_SEVERITY_CRITICAL = "critical"
_SEVERITY_MAJOR = "major"
_SEVERITY_MINOR = "minor"


@dataclass(slots=True)
class PBKDInference:
    character: str
    action: str
    verdict: str        # consistent | contradicts | ambiguous
    dimension: str      # P | B | K | D
    chain: str          # one-sentence reasoning
    severity: str       # critical | major | minor
    evidence: list[str] = field(default_factory=list)


_PBKD_REASON_PROMPT = """\
You are a character consistency analyzer for a narrative system.

Analyze the SCENE TEXT and determine whether each character's actions are \
consistent with their PBKD (Personality, Belief, Knowledge, Desire) profile.

Return ONLY valid JSON — no markdown, no extra text.

CHARACTER PROFILES:
{character_profiles}

SCENE TEXT:
{scene_text}

Instructions:
- For each character who has a meaningful action or reaction in the scene, \
  analyze their behavior against their PBKD profile.
- If a character does not appear or has no clear action, skip them.
- Write the "chain" field in the same language as the PBKD data.

Return JSON:
{{
  "inferences": [
    {{
      "character": "<name exactly as given>",
      "action": "<specific action or behavior observed in the scene>",
      "verdict": "<consistent|contradicts|ambiguous>",
      "dimension": "<P|B|K|D — which PBKD dimension is most relevant>",
      "chain": "<one sentence explaining which PBKD item supports/contradicts this action>",
      "severity": "<critical|major|minor — only meaningful when verdict is 'contradicts'>"
    }}
  ]
}}

Severity rules (when verdict = "contradicts"):
- critical: action directly opposes a core belief or desire
- major: action contradicts the character's personality pattern
- minor: small or contextually excusable mismatch
"""


def _format_character_profiles(char_pbkd: dict[str, dict[str, list[str]]]) -> str:
    lines: list[str] = []
    for name, pbkd in char_pbkd.items():
        lines.append(f"=== {name} ===")
        if pbkd.get("personality"):
            lines.append(f"  Personality (P): {', '.join(pbkd['personality'])}")
        if pbkd.get("beliefs"):
            lines.append(f"  Beliefs (B): {', '.join(pbkd['beliefs'])}")
        if pbkd.get("knowledge"):
            lines.append(f"  Knowledge (K): {', '.join(pbkd['knowledge'])}")
        if pbkd.get("desires"):
            lines.append(f"  Desires (D): {', '.join(pbkd['desires'])}")
        lines.append("")
    return "\n".join(lines)


def _heuristic_reason(
    scene_text: str,
    char_pbkd: dict[str, dict[str, list[str]]],
) -> list[PBKDInference]:
    """
    Fallback when no LLM. Uses simple keyword overlap between PBKD and scene.
    Only flags clear betrayal/death events against pacifist/loyal beliefs.
    """
    from backend.narrative.mutation.models import EventType

    inferences: list[PBKDInference] = []
    lower_scene = scene_text.lower()

    betrayal_cues = {"배신", "배반", "betra", "treachery", "treacher"}
    murder_cues = {"살해", "죽였", "murder", "killed", "slew"}
    revenge_cues = {"복수", "원수", "revenge", "vengeance"}

    for name, pbkd in char_pbkd.items():
        name_in_scene = name.lower() in lower_scene
        if not name_in_scene:
            continue

        beliefs_lower = [b.lower() for b in pbkd.get("beliefs", [])]
        personality_lower = [p.lower() for p in pbkd.get("personality", [])]

        # Check if character performs betrayal against loyal/trust beliefs
        char_before_verb = _char_precedes_verb(name, betrayal_cues, scene_text)
        if char_before_verb:
            loyalty_belief = next(
                (b for b in beliefs_lower if any(
                    token in b for token in ("동료", "신뢰", "loyal", "trust", "protect", "지켜")
                )),
                None,
            )
            if loyalty_belief:
                inferences.append(PBKDInference(
                    character=name,
                    action=char_before_verb,
                    verdict=_VERDICT_CONTRADICTS,
                    dimension="B",
                    chain=f"{name}의 belief '{loyalty_belief}'과 배신 행동이 모순됩니다.",
                    severity=_SEVERITY_CRITICAL,
                    evidence=[loyalty_belief],
                ))

        # Check if revenge-seeker is blocked from taking revenge
        if any(cue in lower_scene for cue in revenge_cues):
            no_revenge_belief = next(
                (b for b in beliefs_lower if any(
                    token in b for token in ("복수", "정의", "revenge is not", "복수는")
                )),
                None,
            )
            if no_revenge_belief and _char_precedes_verb(name, revenge_cues, scene_text):
                inferences.append(PBKDInference(
                    character=name,
                    action="복수를 행함",
                    verdict=_VERDICT_CONTRADICTS,
                    dimension="B",
                    chain=f"{name}의 belief '{no_revenge_belief}'과 복수 행동이 모순됩니다.",
                    severity=_SEVERITY_MAJOR,
                    evidence=[no_revenge_belief],
                ))

    return inferences


def _char_precedes_verb(name: str, verb_cues: set[str], scene_text: str) -> str | None:
    """Return the verb phrase if character name appears within 40 chars before a verb cue."""
    lower_scene = scene_text.lower()
    lower_name = name.lower()
    for cue in verb_cues:
        pos = lower_scene.find(cue)
        while pos != -1:
            window = lower_scene[max(0, pos - 40):pos]
            if lower_name in window:
                return scene_text[pos: pos + len(cue) + 8].strip()
            pos = lower_scene.find(cue, pos + 1)
    return None


class PBKDReasoner:
    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self._llm = llm_provider

    def reason(
        self,
        scene_text: str,
        character_names: list[str],
        character_repo: Any,
    ) -> list[PBKDInference]:
        """
        Load author-defined PBKD for each character and infer consistency.

        Reads metadata_json["pbkd"], NOT metadata_json["memory"].
        The "pbkd" key is set by the frontend PBKD Editor and represents
        the author's deliberate character design.
        """
        if not character_names or not scene_text.strip():
            return []

        try:
            all_chars = character_repo.list()
        except Exception as exc:
            logger.warning("PBKDReasoner: failed to load characters: %s", exc)
            return []

        name_lower_set = {n.lower() for n in character_names}
        char_pbkd: dict[str, dict[str, list[str]]] = {}

        for char in all_chars:
            if char.name.lower() not in name_lower_set:
                continue
            # PBKD is stored scattered: traits=Personality, metadata=Beliefs/Knowledge/Desires
            meta = char.metadata_json if isinstance(char.metadata_json, dict) else {}
            personality = list(char.traits or [])
            beliefs = [str(b) for b in (meta.get("beliefs") or [])]
            knowledge = [str(k) for k in (meta.get("knowledge") or [])]
            desires = [str(d) for d in (meta.get("desires") or char.goals or [])]
            has_data = any([personality, beliefs, knowledge, desires])
            if has_data:
                char_pbkd[char.name] = {
                    "personality": personality,
                    "beliefs": beliefs,
                    "knowledge": knowledge,
                    "desires": desires,
                }

        if not char_pbkd:
            logger.debug("PBKDReasoner: no PBKD data found for characters %s", character_names)
            return []

        if self._llm is not None:
            try:
                return self._llm_reason(scene_text, char_pbkd)
            except Exception as exc:
                logger.warning("PBKDReasoner: LLM inference failed, falling back: %s", exc)

        return _heuristic_reason(scene_text, char_pbkd)

    def _llm_reason(
        self,
        scene_text: str,
        char_pbkd: dict[str, dict[str, list[str]]],
    ) -> list[PBKDInference]:
        profiles = _format_character_profiles(char_pbkd)
        prompt = _PBKD_REASON_PROMPT.format(
            character_profiles=profiles,
            scene_text=scene_text,
        )
        response = self._llm.complete([
            LLMMessage(
                role="system",
                content=(
                    "You are a precise character consistency analyzer. "
                    "Return only valid JSON. No markdown."
                ),
            ),
            LLMMessage(role="user", content=prompt),
        ])
        return self._parse_response(response.content)

    def _parse_response(self, raw: str) -> list[PBKDInference]:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not m:
                logger.warning("PBKDReasoner: cannot parse LLM response: %s", raw[:200])
                return []
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                return []

        inferences: list[PBKDInference] = []
        for item in data.get("inferences", []):
            if not isinstance(item, dict):
                continue
            character = str(item.get("character") or "").strip()
            action = str(item.get("action") or "").strip()
            verdict = str(item.get("verdict") or _VERDICT_AMBIGUOUS).lower()
            dimension = str(item.get("dimension") or "B").upper()
            chain = str(item.get("chain") or "").strip()
            severity = str(item.get("severity") or _SEVERITY_MINOR).lower()

            if not character or not action or not chain:
                continue
            if verdict not in (_VERDICT_CONSISTENT, _VERDICT_CONTRADICTS, _VERDICT_AMBIGUOUS):
                verdict = _VERDICT_AMBIGUOUS
            if dimension not in ("P", "B", "K", "D"):
                dimension = "B"
            if severity not in (_SEVERITY_CRITICAL, _SEVERITY_MAJOR, _SEVERITY_MINOR):
                severity = _SEVERITY_MINOR

            inferences.append(PBKDInference(
                character=character,
                action=action,
                verdict=verdict,
                dimension=dimension,
                chain=chain,
                severity=severity,
            ))

        logger.debug(
            "PBKDReasoner: %d inferences (%d contradictions)",
            len(inferences),
            sum(1 for i in inferences if i.verdict == _VERDICT_CONTRADICTS),
        )
        return inferences
