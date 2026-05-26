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

    def as_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "blocking_issues": self.blocking_issues,
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
        return MultiAgentAnalysisReport(agents=agents, summary=summary, blocking_issues=blocking)