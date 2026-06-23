from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EvidenceChain:
    rule_id: str
    severity: str
    message: str
    confidence: float
    provenance: str
    evidence: list[str] = field(default_factory=list)


class ExplainableReasoningEngine:
    def _base_confidence(self, severity: str) -> float:
        sev = (severity or "warning").lower()
        if sev == "error":
            return 0.92
        if sev == "warning":
            return 0.74
        return 0.58

    def _confidence_with_evidence(self, severity: str, evidence: list[str]) -> float:
        score = self._base_confidence(severity)
        score += min(0.08, 0.02 * len([item for item in evidence if item]))
        return round(max(0.01, min(0.99, score)), 4)

    def build(
        self,
        semantic_issues: list[Any],
        drift_issues: list[Any],
        canon_conflicts: list[Any],
        chronology_conflicts: list[str],
        multi_agent_report: Any,
    ) -> dict[str, Any]:
        traces: list[EvidenceChain] = []

        for issue in semantic_issues:
            evidence = list(getattr(issue, "evidence", []) or [])
            traces.append(EvidenceChain(
                rule_id=str(getattr(issue, "rule_id", "semantic_issue")),
                severity=str(getattr(issue, "severity", "warning")),
                message=str(getattr(issue, "message", "")),
                confidence=self._confidence_with_evidence(str(getattr(issue, "severity", "warning")), evidence),
                provenance="semantic_validator",
                evidence=evidence,
            ))

        for issue in drift_issues:
            evidence = list(getattr(issue, "evidence", []) or [])
            traces.append(EvidenceChain(
                rule_id=str(getattr(issue, "rule_id", "character_drift")),
                severity=str(getattr(issue, "severity", "warning")),
                message=str(getattr(issue, "message", "")),
                confidence=self._confidence_with_evidence(str(getattr(issue, "severity", "warning")), evidence),
                provenance="drift_detector",
                evidence=evidence,
            ))

        for conflict in canon_conflicts:
            traces.append(EvidenceChain(
                rule_id=str(getattr(conflict, "rule_id", "canon_conflict")),
                severity=str(getattr(conflict, "severity", "warning")),
                message=str(getattr(conflict, "message", "")),
                confidence=self._confidence_with_evidence(str(getattr(conflict, "severity", "warning")), []),
                provenance="canon_protection_layer",
                evidence=list(getattr(conflict, "entities", []) or []),
            ))

        for index, conflict in enumerate(chronology_conflicts):
            traces.append(EvidenceChain(
                rule_id=f"timeline_conflict_{index + 1}",
                severity="error",
                message=str(conflict),
                confidence=self._confidence_with_evidence("error", [str(conflict)]),
                provenance="timeline_engine",
                evidence=[str(conflict)],
            ))

        if multi_agent_report is not None:
            payload = multi_agent_report.as_dict() if hasattr(multi_agent_report, "as_dict") else {}
            for agent_name, agent_data in (payload.get("agents") or {}).items():
                for finding in list((agent_data or {}).get("findings") or []):
                    traces.append(EvidenceChain(
                        rule_id=f"agent_{agent_name}",
                        severity="info",
                        message=str(finding),
                        confidence=self._confidence_with_evidence("info", [str(finding)]),
                        provenance=f"multi_agent.{agent_name}",
                        evidence=[str(finding)],
                    ))

        confidence_values = [trace.confidence for trace in traces]
        aggregate_confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 1.0

        return {
            "aggregate_confidence": aggregate_confidence,
            "trace_count": len(traces),
            "evidence_chains": [
                {
                    "rule_id": trace.rule_id,
                    "severity": trace.severity,
                    "message": trace.message,
                    "confidence": trace.confidence,
                    "provenance": trace.provenance,
                    "evidence": trace.evidence,
                }
                for trace in traces
            ],
            "causality": {
                "semantic": len(semantic_issues),
                "drift": len(drift_issues),
                "canon": len(canon_conflicts),
                "timeline": len(chronology_conflicts),
            },
        }
