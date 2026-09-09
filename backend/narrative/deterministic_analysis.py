from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from backend.consistency import MultiAgentNarrativeAnalyzer, SemanticValidator
from backend.consistency.agents import CharacterAgent, CriticAgent, LoreAgent, TimelineAgent

if TYPE_CHECKING:
    from backend.narrative.reasoning.pbkd_reasoner import PBKDInference


@dataclass(slots=True)
class DeterministicAnalysisBundle:
    semantic_result: Any
    multi_agent_report: Any
    normalized_references: list[str]


class DeterministicNarrativeAnalyzer:
    def __init__(self) -> None:
        self._semantic = SemanticValidator(llm_provider=None)
        self._agents = MultiAgentNarrativeAnalyzer(
            lore_agent=LoreAgent(llm_provider=None),
            character_agent=CharacterAgent(llm_provider=None),
            timeline_agent=TimelineAgent(llm_provider=None),
            critic_agent=CriticAgent(llm_provider=None),
        )

    def normalize_references(self, references: list[str], limit: int = 12, max_length: int = 320) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in references:
            compact = " ".join(str(item).split())[:max_length]
            if not compact:
                continue
            key = compact.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(compact)
            if len(normalized) >= limit:
                break
        return normalized

    def order_events(self, events: list[Any]) -> list[Any]:
        return sorted(
            events,
            key=lambda event: (
                str(getattr(event, "timestamp", "")),
                str(getattr(getattr(event, "event_type", None), "value", getattr(event, "event_type", ""))),
                str(getattr(event, "subject", "")),
                str(getattr(event, "predicate", "")),
            ),
        )

    def analyze(
        self,
        scene_text: str,
        references: list[str],
        events: list[Any],
        character_names: list[str],
        character_memories: dict[str, Any],
        canon_conflicts: list[Any],
        drift_issues: list[Any],
        chronology_conflicts: list[str],
        flashback_count: int,
        flash_forward_count: int,
        pbkd_inferences: list[PBKDInference] | None = None,
    ) -> DeterministicAnalysisBundle:
        normalized_references = self.normalize_references(references)
        semantic_result = self._semantic.validate(
            scene_text,
            references=normalized_references,
            events=events,
            character_memories=character_memories,
            pbkd_inferences=pbkd_inferences,
        )
        multi_agent_report = self._agents.analyze(
            scene_text,
            events=events,
            references=normalized_references,
            character_names=character_names,
            character_memories=character_memories,
            canon_conflicts=canon_conflicts,
            drift_issues=drift_issues,
            chronology_conflicts=chronology_conflicts,
            flashback_count=flashback_count,
            flash_forward_count=flash_forward_count,
            semantic_issues=semantic_result.issues,
        )
        return DeterministicAnalysisBundle(
            semantic_result=semantic_result,
            multi_agent_report=multi_agent_report,
            normalized_references=normalized_references,
        )