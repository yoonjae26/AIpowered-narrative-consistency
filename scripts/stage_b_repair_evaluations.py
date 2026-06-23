from __future__ import annotations

import argparse
import json
import re
import statistics
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from fastapi.testclient import TestClient

from backend.main import app


@dataclass(slots=True)
class RepairCase:
    case_id: str
    title: str
    source_text: str
    pbkd_concepts: list[list[str]]
    canon_facts: list[str]


def _repair_cases() -> list[RepairCase]:
    return [
        RepairCase(
            case_id="ko_pbkd_water_fear",
            title="Korean PBKD fear conflict",
            source_text=(
                "민수는 물을 매우 무서워한다. 그는 바다 근처에 가는 것도 피한다.\n\n"
                "폭풍이 몰아치자 민수는 아무런 망설임 없이 바다로 뛰어들었다."
            ),
            pbkd_concepts=[["민수"], ["물을 매우 무서워", "물을 무서워", "두려움", "두려움을 억누르며"]],
            canon_facts=["민수"],
        ),
        RepairCase(
            case_id="canon_resurrection",
            title="Canon resurrection pressure",
            source_text=(
                "The codex states that resurrection is forbidden in this kingdom.\n\n"
                "Mira brings Anna back to life in front of the council."
            ),
            pbkd_concepts=[["Mira"], ["Anna"]],
            canon_facts=["resurrection is forbidden", "Mira", "Anna"],
        ),
        RepairCase(
            case_id="logic_absolutes",
            title="Absolute contradiction",
            source_text=(
                "John always tells the truth to his allies.\n\n"
                "In the same breath, John says he never tells the truth to anyone."
            ),
            pbkd_concepts=[["John"]],
            canon_facts=["John"],
        ),
        RepairCase(
            case_id="kg_relation_consistency",
            title="Relation consistency under patch",
            source_text=(
                "John loves Anna and fears King. John lives in Castle.\n\n"
                "John always protects Anna, but he says he never protects Anna."
            ),
            pbkd_concepts=[["John"], ["Anna"], ["King"]],
            canon_facts=["John loves Anna", "fears King", "lives in Castle"],
        ),
        RepairCase(
            case_id="ko_style_preservation",
            title="Korean style preservation",
            source_text=(
                "유리는 침착하고 조심스러운 성격이다.\n\n"
                "그러나 위기 앞에서 유리는 아무 생각 없이 문을 박차고 나갔다."
            ),
            pbkd_concepts=[["유리"], ["침착", "조심"]],
            canon_facts=["유리"],
        ),
        RepairCase(
            case_id="dialogue_consistency",
            title="Dialogue contradiction",
            source_text=(
                "Anna whispers, 'I trust Mira with my life.'\n\n"
                "Moments later, Anna says she has never trusted Mira at all."
            ),
            pbkd_concepts=[["Anna"], ["Mira"]],
            canon_facts=["Anna", "Mira"],
        ),
    ]


def _issue_signature(issue: dict[str, Any]) -> tuple[str, str]:
    return (str(issue.get("type") or ""), str(issue.get("location") or ""))


def _paragraph_by_location(text: str, location: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]
    match = re.match(r"^paragraph_(\d+)$", location)
    if not match:
        return text
    index = int(match.group(1)) - 1
    if index < 0 or index >= len(paragraphs):
        return text
    return paragraphs[index]


def _normalize_selected_patches(source_text: str, issues: list[dict[str, Any]], patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issue_by_id = {str(item.get("issue_id") or ""): item for item in issues}
    normalized: list[dict[str, Any]] = []
    for patch in patches:
        candidate = dict(patch)
        issue = issue_by_id.get(str(candidate.get("issue_id") or ""), {})
        location = str(candidate.get("location") or issue.get("location") or "paragraph_1")
        paragraph = _paragraph_by_location(source_text, location)
        replace_text = str(candidate.get("replace") or "")
        with_text = str(candidate.get("with") or "")
        if replace_text not in paragraph:
            hint = str(issue.get("replace_hint") or "")
            if hint and hint in paragraph:
                candidate["replace"] = hint
        if not with_text:
            candidate["with"] = str(issue.get("with_hint") or "")
        normalized.append(candidate)
    return normalized


def _pbkd_preserved(source_text: str, patched_text: str, concepts: list[list[str]]) -> bool:
    if not concepts:
        return True
    source_lower = source_text.lower()
    patched_lower = patched_text.lower()
    for variants in concepts:
        source_present = any(variant.lower() in source_lower for variant in variants)
        if not source_present:
            continue
        patched_present = any(variant.lower() in patched_lower for variant in variants)
        if not patched_present:
            return False
    return True


def _canon_preserved(patched_text: str, canon_facts: list[str]) -> bool:
    if not canon_facts:
        return True
    lowered = patched_text.lower()
    return all(fact.lower() in lowered for fact in canon_facts)


def _style_similarity(source_text: str, patched_text: str) -> float:
    return SequenceMatcher(a=source_text, b=patched_text).ratio()


def _auto_decisions(selected_patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for patch in selected_patches:
        replace_text = str(patch.get("replace") or "")
        with_text = str(patch.get("with") or "")
        verification = patch.get("verification") if isinstance(patch, dict) else {}
        accepted = bool(isinstance(verification, dict) and verification.get("accepted"))
        if replace_text and with_text:
            decisions.append(
                {
                    "patch_id": str(patch.get("patch_id") or ""),
                    "action": "accept",
                }
            )
            continue
        decisions.append(
            {
                "patch_id": str(patch.get("patch_id") or ""),
                "action": "accept" if accepted else "reject",
            }
        )
    return decisions


def _evaluate_case(client: TestClient, case: RepairCase, candidates_per_issue: int, style_threshold: float) -> dict[str, Any]:
    structured_payload = {
        "source_text": case.source_text,
        "scene_title": case.title,
        "instructions": "Fix only verified issues; preserve author voice and canon anchors.",
        "preserve_canon": True,
        "preserve_characters": True,
        "max_issues": 6,
        "candidates_per_issue": candidates_per_issue,
        "auto_apply": False,
        "strict_reverification": True,
        "use_knowledge_graph_evidence": True,
        "style_notes": ["minimal intervention", "preserve pacing"],
    }
    structured_resp = client.post("/narrative/rewrite/structured", json=structured_payload)
    structured_resp.raise_for_status()
    structured = structured_resp.json()

    initial_issues = list(structured.get("issues") or [])
    selected_patches = list(structured.get("selected_patches") or [])
    selected_patches = _normalize_selected_patches(case.source_text, initial_issues, selected_patches)
    explainable_complete = 0
    for patch in selected_patches:
        explainable = patch.get("explainable_repair") if isinstance(patch, dict) else {}
        if not isinstance(explainable, dict):
            continue
        required = ["issue", "evidence", "reasoning", "patch", "why_this_patch"]
        if all(key in explainable and explainable.get(key) not in (None, "") for key in required):
            explainable_complete += 1

    decisions = _auto_decisions(selected_patches)
    review_payload = {
        "source_text": case.source_text,
        "scene_title": case.title,
        "instructions": "Apply only accepted patches after re-verification.",
        "preserve_canon": True,
        "preserve_characters": True,
        "strict_reverification": True,
        "patches": selected_patches,
        "decisions": decisions,
        "style_notes": ["minimal intervention", "preserve pacing"],
    }
    review_resp = client.post("/narrative/rewrite/structured/review", json=review_payload)
    review_resp.raise_for_status()
    review = review_resp.json()

    final_issues = list(review.get("final_issues") or [])
    patched_text = str(review.get("patched_text") or case.source_text)

    initial_signatures = {_issue_signature(issue) for issue in initial_issues}
    final_signatures = {_issue_signature(issue) for issue in final_issues}

    repaired_signatures = initial_signatures.difference(final_signatures)
    new_signatures = final_signatures.difference(initial_signatures)

    initial_canon = sum(1 for issue in initial_issues if str(issue.get("type")) == "canon_conflict")
    final_canon = sum(1 for issue in final_issues if str(issue.get("type")) == "canon_conflict")

    style_similarity = _style_similarity(case.source_text, patched_text)
    style_preserved = style_similarity >= style_threshold
    pbkd_preserved = _pbkd_preserved(case.source_text, patched_text, case.pbkd_concepts)
    canon_preserved = _canon_preserved(patched_text, case.canon_facts) and final_canon <= initial_canon

    accepted_count = len(review.get("accepted_patches") or [])
    rejected_count = len(review.get("rejected_patches") or [])

    return {
        "case_id": case.case_id,
        "title": case.title,
        "input_excerpt": case.source_text[:220],
        "initial_issue_count": len(initial_issues),
        "final_issue_count": len(final_issues),
        "repaired_issue_count": len(repaired_signatures),
        "new_issue_count": len(new_signatures),
        "repair_success": len(repaired_signatures) > 0,
        "false_repair": len(new_signatures) > 0,
        "canon_preserved": canon_preserved,
        "style_preserved": style_preserved,
        "style_similarity": round(style_similarity, 4),
        "pbkd_preserved": pbkd_preserved,
        "selected_patch_count": len(selected_patches),
        "accepted_patch_count": accepted_count,
        "rejected_patch_count": rejected_count,
        "explainable_patch_count": explainable_complete,
        "total_patch_count": len(selected_patches),
        "knowledge_graph_evidence_count": len(structured.get("knowledge_graph_evidence") or []),
        "review": {
            "accepted": review.get("accepted_patches") or [],
            "rejected": review.get("rejected_patches") or [],
            "risk_notes": review.get("risk_notes") or [],
        },
        "structured": {
            "risk_notes": structured.get("risk_notes") or [],
            "accepted_candidate_count": structured.get("accepted_candidate_count", 0),
        },
    }


def evaluate_stage_b(cases: list[RepairCase], candidates_per_issue: int, style_threshold: float) -> dict[str, Any]:
    client = TestClient(app)
    case_results: list[dict[str, Any]] = []

    for case in cases:
        case_results.append(_evaluate_case(client, case, candidates_per_issue, style_threshold))

    total_initial_issues = sum(item["initial_issue_count"] for item in case_results)
    total_repaired_issues = sum(item["repaired_issue_count"] for item in case_results)
    total_new_issues = sum(item["new_issue_count"] for item in case_results)

    repair_success_rate = round(total_repaired_issues / max(total_initial_issues, 1), 4)
    false_repair_rate = round(total_new_issues / max(total_repaired_issues + total_new_issues, 1), 4)
    canon_preservation_rate = round(sum(1 for item in case_results if item["canon_preserved"]) / max(len(case_results), 1), 4)
    style_preservation_rate = round(sum(1 for item in case_results if item["style_preserved"]) / max(len(case_results), 1), 4)
    pbkd_preservation_rate = round(sum(1 for item in case_results if item["pbkd_preserved"]) / max(len(case_results), 1), 4)

    style_scores = [item["style_similarity"] for item in case_results]
    explainable_total = sum(item["explainable_patch_count"] for item in case_results)
    patch_total = sum(item["total_patch_count"] for item in case_results)

    return {
        "stage": "Stage B - Narrative Repair Evaluation",
        "metrics": {
            "repair_success_rate": repair_success_rate,
            "false_repair_rate": false_repair_rate,
            "canon_preservation_rate": canon_preservation_rate,
            "style_preservation_rate": style_preservation_rate,
            "pbkd_preservation_rate": pbkd_preservation_rate,
            "average_style_similarity": round(statistics.mean(style_scores), 4) if style_scores else 0.0,
            "explainable_repair_coverage": round(explainable_total / max(patch_total, 1), 4),
        },
        "totals": {
            "cases": len(case_results),
            "initial_issues": total_initial_issues,
            "repaired_issues": total_repaired_issues,
            "new_issues": total_new_issues,
            "total_patches": patch_total,
        },
        "thresholds": {
            "style_similarity_threshold": style_threshold,
            "candidates_per_issue": candidates_per_issue,
        },
        "case_results": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage B narrative repair evaluation.")
    parser.add_argument("--style-threshold", type=float, default=0.82)
    parser.add_argument("--candidates-per-issue", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="Limit number of evaluation cases. 0 means all cases.")
    args = parser.parse_args()

    cases = _repair_cases()
    if args.limit > 0:
        cases = cases[: args.limit]

    report = evaluate_stage_b(
        cases=cases,
        candidates_per_issue=max(1, args.candidates_per_issue),
        style_threshold=args.style_threshold,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
