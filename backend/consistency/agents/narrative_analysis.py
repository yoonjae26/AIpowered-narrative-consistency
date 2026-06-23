from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.consistency.agents.character_agent import CharacterAgent
from backend.consistency.agents.critic_agent import CriticAgent
from backend.consistency.agents.lore_agent import LoreAgent
from backend.consistency.agents.timeline_agent import TimelineAgent


@dataclass(slots=True)
class AgentAnalysis:
    agent: str
    role: str
    findings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MultiAgentAnalysisReport:
    agents: list[AgentAnalysis] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    structured_summary: list[dict[str, object]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "blocking_issues": self.blocking_issues,
            "structured_summary": self.structured_summary,
            "agents": {
                item.agent: {
                    "role": item.role,
                    "findings": item.findings,
                }
                for item in self.agents
            },
        }


class MultiAgentNarrativeAnalyzer:
    def __init__(
        self,
        lore_agent: LoreAgent | None = None,
        character_agent: CharacterAgent | None = None,
        timeline_agent: TimelineAgent | None = None,
        critic_agent: CriticAgent | None = None,
    ) -> None:
        self._lore = lore_agent or LoreAgent()
        self._character = character_agent or CharacterAgent()
        self._timeline = timeline_agent or TimelineAgent()
        self._critic = critic_agent or CriticAgent()

    def analyze(
        self,
        text: str,
        events: list[Any],
        references: list[str],
        character_names: list[str],
        character_memories: dict[str, Any],
        canon_conflicts: list[Any],
        drift_issues: list[Any],
        chronology_conflicts: list[str],
        flashback_count: int,
        flash_forward_count: int,
        semantic_issues: list[Any],
    ) -> MultiAgentAnalysisReport:
        agents = [
            AgentAnalysis(
                agent="lore",
                role="canon",
                findings=self._lore.analyze(text, references=references, canon_conflicts=canon_conflicts),
            ),
            AgentAnalysis(
                agent="character",
                role="personality",
                findings=self._character.analyze(
                    text,
                    character_names,
                    character_memories=character_memories,
                    drift_issues=drift_issues,
                ),
            ),
            AgentAnalysis(
                agent="timeline",
                role="chronology",
                findings=self._timeline.analyze(
                    events,
                    scene_text=text,
                    chronology_conflicts=chronology_conflicts,
                    flashback_count=flashback_count,
                    flash_forward_count=flash_forward_count,
                ),
            ),
            AgentAnalysis(
                agent="critic",
                role="pacing",
                findings=self._critic.analyze(text, events, semantic_issues=semantic_issues),
            ),
        ]
        summary = [f"{item.agent}: {item.findings[0]}" for item in agents if item.findings]
        if not summary:
            summary = ["No major issues detected by the multi-agent panel."]
        blocking = [
            finding
            for item in agents
            for finding in item.findings
            if any(token in finding.lower() for token in ("conflict", "contradict", "forbid", "impossible", "dead"))
        ]
        structured = [self._structured_agent_summary(item) for item in agents]
        return MultiAgentAnalysisReport(agents=agents, summary=summary, blocking_issues=blocking, structured_summary=structured)

    def _structured_agent_summary(self, item: AgentAnalysis) -> dict[str, object]:
        findings = [entry for entry in item.findings if entry.strip()]
        severity = self._severity_from_findings(findings)
        issue_count = len(findings)
        risk = {
            "critical": "high",
            "major": "medium",
            "minor": "low",
            "none": "low",
        }[severity]

        penalties = {
            "critical": 0.45,
            "major": 0.25,
            "minor": 0.08,
            "none": 0.0,
        }
        score = max(0.05, min(0.99, 1.0 - penalties[severity] - min(issue_count, 5) * 0.04))

        return {
            "agent": item.agent,
            "role": item.role,
            "score": round(score, 2),
            "primary_trait": self._primary_trait(item.agent, findings),
            "risk": risk,
            "severity": severity,
            "issue_count": issue_count,
        }

    def _severity_from_findings(self, findings: list[str]) -> str:
        if not findings:
            return "none"
        lowered = " ".join(entry.lower() for entry in findings)
        if any(token in lowered for token in ("impossible", "forbidden", "contradict", "dead", "immutable canon")):
            return "critical"
        if any(token in lowered for token in ("conflict", "abrupt", "collapse", "inconsistent", "compressed")):
            return "major"
        return "minor"

    def _primary_trait(self, agent: str, findings: list[str]) -> str:
        lowered = " ".join(entry.lower() for entry in findings)
        if agent == "character":
            if "betray" in lowered or "trust" in lowered:
                return "trust_instability"
            if "emotion" in lowered or "joy" in lowered or "grief" in lowered:
                return "emotion_shift"
            return "character_consistency"
        if agent == "timeline":
            if "flashback" in lowered:
                return "flashback_density"
            if "flash-forward" in lowered:
                return "future_anchor"
            if "conflict" in lowered:
                return "chronology_conflict"
            return "chronology_stable"
        if agent == "critic":
            if "abrupt" in lowered or "compressed" in lowered:
                return "pacing_abrupt"
            if "forced" in lowered:
                return "forced_escalation"
            return "pacing_stable"
        if agent == "lore":
            if "conflict" in lowered or "canon" in lowered:
                return "canon_alignment"
            return "lore_stable"
        return "general_consistency"