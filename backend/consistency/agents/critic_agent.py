from __future__ import annotations

import re
from typing import Any

from backend.llm.providers.base import BaseLLMProvider, LLMMessage
from backend.narrative.mutation.models import EventType


class CriticAgent:
    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self._llm = llm_provider

    def analyze(
        self,
        text: str,
        events: list[Any],
        semantic_issues: list[Any] | None = None,
    ) -> list[str]:
        findings: list[str] = []
        lower = text.lower()
        intense_types = {
            EventType.MURDER,
            EventType.DEATH,
            EventType.BETRAYAL,
            EventType.CAPTURE,
            EventType.ESCAPE,
            EventType.RESURRECTION,
        }
        intense_count = sum(1 for event in events if getattr(event, "event_type", None) in intense_types)
        if intense_count >= 2 and not re.search(r"\b(after|later|meanwhile|the next day|hours later|once)\b", lower):
            findings.append("Pacing escalates through multiple high-intensity turns without much breathing room.")
        if lower.count("suddenly") >= 2:
            findings.append("Repeated 'suddenly' beats make the pacing feel forced instead of earned.")
        for issue in semantic_issues or []:
            if getattr(issue, "category", "") == "unnatural_progression":
                findings.append(issue.message)

        if self._llm is not None:
            try:
                prompt = "\n".join([
                    f"Scene: {text}",
                    "Events:",
                    *[getattr(event, "predicate", str(event)) for event in events],
                    "Return short bullet findings about pacing and dramatic flow.",
                ])
                response = self._llm.complete([
                    LLMMessage(role="system", content="You are a pacing critic for fiction scenes."),
                    LLMMessage(role="user", content=prompt),
                ])
                findings.extend(line.strip("- ") for line in response.content.splitlines() if line.strip())
            except Exception:
                pass

        return list(dict.fromkeys(findings))