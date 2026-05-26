from __future__ import annotations

from typing import Any

from backend.llm.providers.base import BaseLLMProvider, LLMMessage


class LoreAgent:
    def __init__(self, llm_provider: BaseLLMProvider | None = None) -> None:
        self._llm = llm_provider

    def analyze(
        self,
        text: str,
        references: list[str] | None = None,
        canon_conflicts: list[Any] | None = None,
    ) -> list[str]:
        findings = [conflict.message for conflict in (canon_conflicts or [])]
        if not findings and references:
            findings.append(f"Reviewed {len(references)} lore/canon references with no direct canon break detected.")

        if self._llm is not None:
            try:
                prompt = "\n".join([
                    f"Scene: {text}",
                    "Reference notes:",
                    *(references or ["none"]),
                    f"Canon conflicts: {[conflict.message for conflict in (canon_conflicts or [])]}",
                    "Return short bullet findings about canon alignment.",
                ])
                response = self._llm.complete([
                    LLMMessage(role="system", content="You are a canon-focused narrative analyst."),
                    LLMMessage(role="user", content=prompt),
                ])
                findings.extend(line.strip("- ") for line in response.content.splitlines() if line.strip())
            except Exception:
                pass

        return list(dict.fromkeys(findings))