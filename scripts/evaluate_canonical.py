#!/usr/bin/env python3
"""
홍길동전 Canonical Dataset Evaluation Script

Measures:
  - Entity Precision / Recall (character extraction)
  - Event Recall (required event types)
  - Adversarial TP / TN (contradiction detection)

Usage:
    python3 scripts/evaluate_canonical.py --chapters 1-10
    python3 scripts/evaluate_canonical.py --chapters 1-60 --adversarial
    python3 scripts/evaluate_canonical.py --chapters 1,6,44 --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "data" / "honggildongjeon_canonical.json"
API_BASE = "http://localhost:8001"
PROCESS_URL = f"{API_BASE}/narrative/state-mutation"


def parse_chapter_range(spec: str) -> list[int]:
    result = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.extend(range(int(a), int(b) + 1))
        else:
            result.append(int(part))
    return sorted(set(result))


def call_api(scene_text: str, scene_title: str, timeout: int = 120, persist: bool = False) -> tuple[dict | None, float, str | None]:
    """Call the pipeline API. Returns (result, elapsed_seconds, error).
    By default dry_run=True so evaluation never corrupts DB state.
    Pass persist=True only when you explicitly want state written to DB.
    """
    payload = {
        "scene_text": scene_text,
        "scene_title": scene_title,
        "context": {"dry_run": not persist},
    }
    t0 = time.time()
    try:
        resp = requests.post(PROCESS_URL, json=payload, timeout=timeout)
        elapsed = time.time() - t0
        if resp.status_code != 200:
            return None, elapsed, f"HTTP {resp.status_code}: {resp.text[:200]}"
        return resp.json(), elapsed, None
    except Exception as e:
        return None, time.time() - t0, str(e)


def _name_matches(detected: str, canonical: str, aliases: dict[str, list[str]]) -> bool:
    """Check if detected name matches a canonical name or its alias."""
    if detected == canonical:
        return True
    # Check canonical aliases
    for canon, alias_list in aliases.items():
        if detected in alias_list and canonical == canon:
            return True
    # Partial: if detected is a suffix of canonical (e.g. "길동" in "홍길동")
    if detected in canonical or canonical.endswith(detected):
        return True
    return False


def evaluate_entity(result: dict, ground_truth: dict) -> dict:
    """Compute entity Precision / Recall.
    API response: entities.characters = list[str]
    Uses alias matching to handle short names (e.g. '길동' → '홍길동').
    """
    entities = result.get("entities", {})
    chars_raw = entities.get("characters", [])
    detected = [c for c in chars_raw if c and isinstance(c, str)]

    expected = list(ground_truth["expected_characters"])
    forbidden = set(ground_truth.get("forbidden_characters", []))
    aliases: dict[str, list[str]] = ground_truth.get("character_aliases", {})

    # Map each detected name to a canonical name (or None if truly unknown)
    def best_canonical(d: str) -> str | None:
        for canon in expected:
            if _name_matches(d, canon, aliases):
                return canon
        return None

    matched_expected: set[str] = set()
    true_pos_detected: list[str] = []
    false_pos_detected: list[str] = []

    for d in detected:
        canon = best_canonical(d)
        if canon:
            matched_expected.add(canon)
            true_pos_detected.append(d)
        elif d not in forbidden:
            false_pos_detected.append(d)

    fn = [c for c in expected if c not in matched_expected]
    fp_forbidden = [d for d in detected if d in forbidden]

    precision = len(true_pos_detected) / len(detected) if detected else 1.0
    recall = len(matched_expected) / len(expected) if expected else 1.0

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "detected": sorted(detected),
        "expected": sorted(expected),
        "true_positives": sorted(true_pos_detected),
        "false_positives": sorted(false_pos_detected),
        "false_negatives": sorted(fn),
        "forbidden_detected": sorted(fp_forbidden),
    }


def evaluate_events(result: dict, ground_truth: dict) -> dict:
    """Check required event types are present.
    API response: events = {"count": int, "types": {type_name: count}}
    """
    events_resp = result.get("events", {})
    if isinstance(events_resp, dict):
        count = events_resp.get("count", 0)
        detected_types = set(events_resp.get("types", {}).keys())
    else:
        # fallback: list of event objects
        count = len(events_resp)
        detected_types = set(e.get("event_type") for e in events_resp if isinstance(e, dict))

    required = set(ground_truth.get("required_event_types", []))
    forbidden = set(ground_truth.get("forbidden_event_types", []))

    covered = required & detected_types
    missing = required - detected_types
    forbidden_found = detected_types & forbidden

    count_min, count_max = ground_truth.get("event_count_range", [0, 999])

    return {
        "count": count,
        "count_in_range": count_min <= count <= count_max,
        "required_covered": sorted(covered),
        "required_missing": sorted(missing),
        "forbidden_found": sorted(forbidden_found),
        "event_recall": round(len(covered) / len(required), 3) if required else 1.0,
        "count_range": [count_min, count_max],
        "detected_types": sorted(detected_types),
    }


def evaluate_pbkd(result: dict, ground_truth: dict) -> dict:
    """Check PBKD contradiction expectations.
    API response: pbkd_reasoning = {"inferences": [], "contradiction_count": int}
                  gate = {"decision": "approve", "approved": bool, ...}
    """
    pbkd = result.get("pbkd_reasoning") or {}
    contradiction_count = pbkd.get("contradiction_count", 0)
    inferences = pbkd.get("inferences", [])

    gate = result.get("gate") or {}
    gate_decision = gate.get("decision", "")
    gate_approved = gate.get("approved", True)

    expected_contradictions = ground_truth.get("expected_contradictions", 0)

    pbkd_correct = (contradiction_count == 0 and expected_contradictions == 0) \
                   or (contradiction_count > 0 and expected_contradictions > 0)

    return {
        "gate_decision": gate_decision,
        "gate_approved": gate_approved,
        "detected_contradictions": contradiction_count,
        "expected_contradictions": expected_contradictions,
        "pbkd_correct": pbkd_correct,
        "inferences_count": len(inferences),
    }


def evaluate_adversarial(result: dict | None, error: str | None, chapter: dict) -> dict:
    """Evaluate adversarial run: did the pipeline flag the corruption?
    API response signals a problem via:
      - pbkd_reasoning.contradiction_count > 0
      - kg_conflicts (non-empty list)
      - quality.major_issues > 0  (or critical_issues > 0)
      - analysis.agent_summary: any agent with severity in [major, critical]
    """
    adv = chapter.get("adversarial") or {}
    corruption_type = adv.get("corruption_type", "")
    expected_agent = adv.get("expected_flag_agent", "")

    if error or result is None:
        return {"result": "error", "error": error, "corruption_type": corruption_type}

    pbkd = result.get("pbkd_reasoning") or {}
    contradiction_count = pbkd.get("contradiction_count", 0)

    kg_conflicts = result.get("kg_conflicts") or []

    quality = result.get("quality") or {}
    major_issues = quality.get("major_issues", 0)
    critical_issues = quality.get("critical_issues", 0)

    analysis = result.get("analysis") or {}
    agents = analysis.get("agent_summary", [])
    agent_flags = [a for a in agents if a.get("severity") in ("major", "critical")]

    flagged = bool(
        contradiction_count > 0
        or kg_conflicts
        or critical_issues > 0
        # major_issues on its own can be a false positive (timeline false positive),
        # so only count it if also pbkd or kg sees an issue
    )

    return {
        "result": "TP" if flagged else "FN",
        "corruption_type": corruption_type,
        "expected_agent": expected_agent,
        "flagged": flagged,
        "pbkd_contradictions": contradiction_count,
        "kg_conflicts": len(kg_conflicts),
        "quality_major": major_issues,
        "quality_critical": critical_issues,
        "flagging_agents": [a["agent"] for a in agent_flags],
        "detail": adv.get("corrupted_detail", ""),
    }


def run_chapter(chapter: dict, run_adversarial: bool = False, verbose: bool = False, persist: bool = False) -> dict:
    ch_no = chapter["chapter"]
    title = chapter["title"]
    gt = chapter["ground_truth"]

    # --- Clean run ---
    result, elapsed, error = call_api(chapter["scene_text"], title, persist=persist)
    clean = {}
    if error or result is None:
        clean = {"error": error}
    else:
        clean = {
            "entity": evaluate_entity(result, gt),
            "events": evaluate_events(result, gt),
            "pbkd": evaluate_pbkd(result, gt),
        }
        if verbose:
            clean["raw"] = result

    report: dict = {
        "chapter": ch_no,
        "title": title,
        "elapsed": round(elapsed, 1),
        "clean": clean,
        "adversarial": None,
    }

    # --- Adversarial run (optional) — always dry_run to avoid corrupting state ---
    if run_adversarial and chapter.get("adversarial"):
        adv_text = chapter["adversarial"]["scene_text"]
        adv_result, adv_elapsed, adv_error = call_api(adv_text, f"[ADV] {title}", persist=False)
        report["adversarial"] = evaluate_adversarial(adv_result, adv_error, chapter)
        report["adversarial"]["elapsed"] = round(adv_elapsed, 1)

    return report


def print_report(r: dict, show_adversarial: bool) -> None:
    ch = r["chapter"]
    title = r["title"][:50]
    clean = r.get("clean", {})

    if "error" in clean:
        print(f"\n❌ [Ch {ch:02d}] {title}  → ERROR: {clean['error']}")
        return

    ent = clean.get("entity", {})
    ev = clean.get("events", {})
    pb = clean.get("pbkd", {})

    ent_ok = ent.get("precision", 0) >= 0.8 and ent.get("recall", 0) >= 0.8
    ev_ok = ev.get("event_recall", 0) >= 0.8 and ev.get("count_in_range", False)
    pb_ok = pb.get("pbkd_correct", False)

    icon = "✅" if (ent_ok and ev_ok and pb_ok) else "⚠️ "
    print(f"\n{icon} [Ch {ch:02d}] {title}  ({r['elapsed']}s)")
    print(f"  Entity : P={ent.get('precision'):.2f} R={ent.get('recall'):.2f}  "
          f"FP={ent.get('false_positives')}  FN={ent.get('false_negatives')}")
    print(f"  Events : count={ev.get('count')}  range={ev.get('count_range')}  "
          f"event_recall={ev.get('event_recall'):.2f}  missing={ev.get('required_missing')}")
    print(f"  PBKD   : contradictions={pb.get('detected_contradictions')}  gate={pb.get('gate_decision')}")

    if show_adversarial and r.get("adversarial"):
        adv = r["adversarial"]
        adv_icon = "🎯" if adv.get("result") == "TP" else "🔴"
        print(f"  Advers.: {adv_icon} {adv.get('result')}  [{adv.get('corruption_type')}]  "
              f"pbkd={adv.get('pbkd_contradictions')} quality_critical={adv.get('quality_critical')}")


def print_summary(reports: list[dict], show_adversarial: bool) -> None:
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)

    entity_precs, entity_recs, event_recs = [], [], []
    adv_tp, adv_fn, adv_total = 0, 0, 0

    for r in reports:
        clean = r.get("clean", {})
        if "error" in clean:
            continue
        ent = clean.get("entity", {})
        ev = clean.get("events", {})
        entity_precs.append(ent.get("precision", 0))
        entity_recs.append(ent.get("recall", 0))
        event_recs.append(ev.get("event_recall", 0))

        if show_adversarial and r.get("adversarial"):
            adv_total += 1
            result = r["adversarial"].get("result")
            if result == "TP":
                adv_tp += 1
            elif result == "FN":
                adv_fn += 1

    def avg(xs): return sum(xs) / len(xs) if xs else 0.0

    n = len(entity_precs)
    print(f"Chapters evaluated : {n}")
    print(f"Entity Precision   : {avg(entity_precs):.3f}  (avg over {n} chapters)")
    print(f"Entity Recall      : {avg(entity_recs):.3f}")
    print(f"Event Recall       : {avg(event_recs):.3f}  (required types covered)")

    if show_adversarial and adv_total > 0:
        adv_rate = adv_tp / adv_total if adv_total else 0
        print(f"\nAdversarial Detection ({adv_total} tests):")
        print(f"  True Positive  : {adv_tp} ({adv_rate:.1%})")
        print(f"  False Negative : {adv_fn} ({1-adv_rate:.1%})")

    # Per-chapter detail
    low_precision = [r for r in reports if r.get("clean", {}).get("entity", {}).get("precision", 1) < 0.8]
    low_recall = [r for r in reports if r.get("clean", {}).get("entity", {}).get("recall", 1) < 0.8]
    if low_precision:
        print(f"\nLow entity precision (<0.8): {[r['chapter'] for r in low_precision]}")
    if low_recall:
        print(f"Low entity recall (<0.8)   : {[r['chapter'] for r in low_recall]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate NarrativeOS on 홍길동전 canonical dataset")
    parser.add_argument("--chapters", default="1-10", help="Chapter numbers: '1-10', '1,6,44', '1-60'")
    parser.add_argument("--adversarial", action="store_true", help="Also run adversarial versions")
    parser.add_argument("--verbose", action="store_true", help="Dump raw API responses")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on first API error")
    parser.add_argument("--no-clean", action="store_true", help="Skip clean run (adversarial only)")
    parser.add_argument("--persist", action="store_true",
                        help="Write scene state to DB (default: dry_run — no DB writes, safe to re-run)")
    args = parser.parse_args()

    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    ch_by_no = {ch["chapter"]: ch for ch in data["chapters"]}

    ch_nos = parse_chapter_range(args.chapters)
    missing = [n for n in ch_nos if n not in ch_by_no]
    if missing:
        print(f"ERROR: Chapters not found: {missing}")
        sys.exit(1)

    print("=" * 70)
    print(f"홍길동전 Canonical Dataset Evaluation")
    print(f"Chapters: {ch_nos}  adversarial={args.adversarial}")
    print(f"API: {PROCESS_URL}")
    print("=" * 70)

    reports = []
    for ch_no in ch_nos:
        chapter = ch_by_no[ch_no]
        print(f"▶ Ch {ch_no:02d} {chapter['title'][:40]} ...", end="", flush=True)

        if args.no_clean:
            report = {"chapter": ch_no, "title": chapter["title"], "elapsed": 0, "clean": {}, "adversarial": None}
        else:
            report = run_chapter(chapter, run_adversarial=args.adversarial, verbose=args.verbose, persist=args.persist)

        reports.append(report)
        print_report(report, show_adversarial=args.adversarial)

        if args.stop_on_error and "error" in report.get("clean", {}):
            print("\n⛔ Stopped due to --stop-on-error")
            break

    print_summary(reports, show_adversarial=args.adversarial)

    # Save results
    spec = args.chapters.replace(",", "_").replace("-", "to")
    suffix = "_adv" if args.adversarial else ""
    out = ROOT / "data" / f"canonical_eval_{spec}{suffix}.json"
    out.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved → {out}")


if __name__ == "__main__":
    main()
