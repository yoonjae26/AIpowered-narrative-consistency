#!/usr/bin/env python3
"""
홍길동전 scene pipeline test script.
Usage:
    python3 scripts/test_pipeline_scenes.py --scenes 1,2,3
    python3 scripts/test_pipeline_scenes.py --scenes 1-10
    python3 scripts/test_pipeline_scenes.py --scenes 1-75
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "honggildongjeon_scenes.json"
API_BASE = "http://localhost:8001"
PROCESS_URL = f"{API_BASE}/narrative/state-mutation"


def build_scene_text(scene: dict) -> str:
    """Combine scene fields into a narrative paragraph for the pipeline."""
    lines = [f"[장면] {scene['title']}"]
    lines.append(scene["summary"])
    for beat in scene["beats"]:
        lines.append(f"- {beat}")
    if scene.get("location"):
        lines.append(f"[배경] {scene['location']}")
    return "\n".join(lines)


def parse_scene_range(spec: str) -> list[int]:
    result = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.extend(range(int(a), int(b) + 1))
        else:
            result.append(int(part))
    return sorted(set(result))


def check_result(scene: dict, result: dict) -> dict:
    """Analyze pipeline result for key quality signals."""
    report = {
        "seq": scene["seq"],
        "title": scene["title"],
        "ok": True,
        "warnings": [],
        "entity": {},
        "events": {},
        "pbkd": {},
        "kg": {},
        "memory": {},
        "consistency": {},
    }

    # Entity
    entities = result.get("entities", {})
    chars_extracted = [c.get("name") for c in entities.get("characters", [])]
    chars_expected = scene["characters"]
    missing = [c for c in chars_expected if not any(c in x for x in chars_extracted)]
    junk = [c for c in chars_extracted if c and len(c) < 2]
    report["entity"] = {
        "extracted": chars_extracted,
        "expected": chars_expected,
        "missing": missing,
        "junk": junk,
    }
    if missing:
        report["warnings"].append(f"ENTITY: missing {missing}")
    if junk:
        report["warnings"].append(f"ENTITY: junk chars {junk}")

    # Events
    events = result.get("events", [])
    event_types = [e.get("event_type") for e in events]
    report["events"] = {
        "count": len(events),
        "types": event_types,
    }
    if len(events) > 30:
        report["warnings"].append(f"EVENTS: too many ({len(events)}) — possible event explosion")
    if len(events) == 0:
        report["warnings"].append("EVENTS: zero events generated")

    # Gate / PBKD
    gate = result.get("gate_decision", {})
    gate_status = gate.get("status") if isinstance(gate, dict) else str(gate)
    pbkd_issues = result.get("pbkd_issues", [])
    report["pbkd"] = {
        "gate_status": gate_status,
        "issues_count": len(pbkd_issues),
        "issues": pbkd_issues[:5],
    }
    if gate_status not in ("pass", "proceed", "allowed", None, ""):
        report["warnings"].append(f"PBKD gate: {gate_status}")

    # KG conflicts
    kg_conflicts = result.get("kg_conflicts", [])
    report["kg"] = {
        "conflicts": kg_conflicts[:5],
        "conflict_count": len(kg_conflicts),
    }
    if kg_conflicts:
        report["warnings"].append(f"KG: {len(kg_conflicts)} conflict(s)")

    # Memory (check if anything was indexed)
    mutation = result.get("mutation_result", {})
    chars_upserted = mutation.get("characters_upserted", []) if isinstance(mutation, dict) else []
    report["memory"] = {
        "characters_upserted": chars_upserted,
    }

    # Consistency
    consistency = result.get("consistency_report", {}) or {}
    if isinstance(consistency, dict):
        cons_issues = consistency.get("issues", [])
        cons_warnings = consistency.get("warnings", [])
    else:
        cons_issues = []
        cons_warnings = []
    report["consistency"] = {
        "issues": cons_issues[:3],
        "warnings": cons_warnings[:3],
    }
    if cons_issues:
        report["warnings"].append(f"CONSISTENCY: {len(cons_issues)} issue(s)")

    if report["warnings"]:
        report["ok"] = False

    return report


def process_scene(scene: dict, verbose: bool = False) -> dict:
    text = build_scene_text(scene)
    payload = {
        "scene_text": text,
        "scene_title": scene["title"],
        "context": {},
    }
    t0 = time.time()
    resp = requests.post(PROCESS_URL, json=payload, timeout=120)
    elapsed = time.time() - t0

    if resp.status_code != 200:
        return {
            "seq": scene["seq"],
            "title": scene["title"],
            "ok": False,
            "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
            "elapsed": elapsed,
        }

    result = resp.json()
    report = check_result(scene, result)
    report["elapsed"] = round(elapsed, 1)
    if verbose:
        report["raw"] = result
    return report


def print_report(report: dict) -> None:
    status = "✅" if report.get("ok") else "⚠️ "
    print(f"\n{status} Scene [{report['seq']:02d}] {report['title']}  ({report.get('elapsed', '?')}s)")

    if "error" in report:
        print(f"  ❌ ERROR: {report['error']}")
        return

    e = report.get("entity", {})
    print(f"  Entity  : extracted={e.get('extracted')}  missing={e.get('missing')}  junk={e.get('junk')}")

    ev = report.get("events", {})
    print(f"  Events  : count={ev.get('count')}  types={ev.get('types')}")

    pb = report.get("pbkd", {})
    print(f"  PBKD    : gate={pb.get('gate_status')}  issues={pb.get('issues_count')}")

    kg = report.get("kg", {})
    print(f"  KG      : conflicts={kg.get('conflict_count')}")

    mem = report.get("memory", {})
    print(f"  Memory  : chars_upserted={mem.get('characters_upserted')}")

    con = report.get("consistency", {})
    print(f"  Consist.: issues={len(con.get('issues', []))}  warnings={len(con.get('warnings', []))}")

    for w in report.get("warnings", []):
        print(f"  ⚠️  {w}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test NarrativeOS pipeline on 홍길동전 scenes")
    parser.add_argument("--scenes", default="1,2,3", help="Scene numbers: '1,2,3' or '1-10' or '1-75'")
    parser.add_argument("--verbose", action="store_true", help="Dump raw API response")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on first failure")
    args = parser.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    all_scenes = {s["seq"]: s for s in data["scenes"]}

    seqs = parse_scene_range(args.scenes)
    missing_seqs = [n for n in seqs if n not in all_scenes]
    if missing_seqs:
        print(f"ERROR: Scene(s) not found: {missing_seqs}")
        sys.exit(1)

    print(f"=== NarrativeOS Pipeline Test ===")
    print(f"Processing {len(seqs)} scene(s): {seqs}")
    print(f"API: {PROCESS_URL}\n")

    reports = []
    for seq in seqs:
        scene = all_scenes[seq]
        print(f"▶ Processing [{seq:02d}] {scene['title']} ...", end="", flush=True)
        report = process_scene(scene, verbose=args.verbose)
        reports.append(report)
        print_report(report)

        if args.stop_on_error and not report.get("ok"):
            print("\n⛔ Stopped due to --stop-on-error")
            break

    ok_count = sum(1 for r in reports if r.get("ok"))
    fail_count = len(reports) - ok_count
    print(f"\n=== Summary: {ok_count}/{len(reports)} passed, {fail_count} warning(s) ===")

    # Save results
    out_path = ROOT / "data" / f"pipeline_test_scenes_{args.scenes.replace(',', '_').replace('-', 'to')}.json"
    out_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Results saved → {out_path}")


if __name__ == "__main__":
    main()
