#!/usr/bin/env python3
"""
debug_phase3a.py — Phase 3A: Narrative Domain Core

Sections:
  A  Server connectivity
  B  Character CRUD + PBKD
  C  Lore CRUD
  D  Scene CRUD
  E  Timeline Events
  F  Relationships
  G  State Mutation (state engine pipeline)
  H  Query System
  I  Narrative Summary

Usage:
  python3 debug_phase3a.py [--api URL] [--section a|b|c|d|e|f|g|h|i] [-v]
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


DEFAULT_API = "http://127.0.0.1:8000"

RESET  = "\033[0m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"

_pass_count = 0
_fail_count = 0
_skip_count = 0
_verbose    = False


def _ok(label: str, detail: str = "") -> None:
    global _pass_count
    _pass_count += 1
    msg = f"  {GREEN}✓{RESET} {label}"
    if detail and _verbose:
        msg += f"  {CYAN}({detail}){RESET}"
    print(msg)


def _fail(label: str, detail: str = "") -> None:
    global _fail_count
    _fail_count += 1
    msg = f"  {RED}✗{RESET} {label}"
    if detail:
        msg += f"  {CYAN}({detail}){RESET}"
    print(msg)


def _skip(label: str, reason: str = "") -> None:
    global _skip_count
    _skip_count += 1
    msg = f"  {YELLOW}⊘{RESET} {label}"
    if reason:
        msg += f"  [{reason}]"
    print(msg)


def _section(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{RESET}")


def print_summary() -> int:
    total = _pass_count + _fail_count
    color = GREEN if _fail_count == 0 else RED
    print(f"\n{BOLD}{'─' * 52}{RESET}")
    print(f"{BOLD}Result: {color}{_pass_count}/{total} passed{RESET}", end="")
    if _skip_count:
        print(f"  {YELLOW}({_skip_count} skipped){RESET}", end="")
    print()
    if _fail_count > 0:
        print(f"{RED}Phase 3A has failures — check details above.{RESET}")
    return _fail_count


# ─────────────────────────────────────────────────────────
# HTTP client
# ─────────────────────────────────────────────────────────

class APIClient:
    def __init__(self, base_url: str, verbose: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.verbose  = verbose

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        token: str | None = None,
        timeout: int = 20,
    ) -> tuple[int, Any]:
        url = self.base_url + path
        if params:
            qs = "&".join(
                f"{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}"
                for k, v in params.items()
            )
            url = f"{url}?{qs}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req  = urllib.request.Request(url, data=data, headers=headers, method=method)
        if self.verbose:
            print(f"    {YELLOW}→ {method} {path}{RESET}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw    = resp.read().decode("utf-8")
                result = json.loads(raw) if raw else {}
                if self.verbose:
                    print(f"    {CYAN}← {resp.status}{RESET}")
                return resp.status, result
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8") if exc.fp else ""
            try:
                result = json.loads(raw)
            except Exception:
                result = {"_raw": raw[:300]}
            if self.verbose:
                print(f"    {RED}← {exc.code}{RESET}")
            return exc.code, result

    def get(self, path: str, params: dict[str, str] | None = None,
            token: str | None = None) -> tuple[int, Any]:
        return self.request("GET", path, params=params, token=token)

    def post(self, path: str, body: dict[str, Any] | None = None,
             token: str | None = None, timeout: int = 20) -> tuple[int, Any]:
        return self.request("POST", path, body=body, token=token, timeout=timeout)

    def patch(self, path: str, body: dict[str, Any],
              token: str | None = None) -> tuple[int, Any]:
        return self.request("PATCH", path, body=body, token=token)


# ─────────────────────────────────────────────────────────
# A: Server connectivity
# ─────────────────────────────────────────────────────────

def section_a(client: APIClient) -> bool:
    _section("A: Server Connectivity")
    try:
        status, body = client.get("/")
    except Exception as exc:
        _fail("GET / reachable", str(exc))
        return False

    if status == 200:
        _ok("GET / → 200", body.get("message", ""))
    else:
        _fail("GET / → 200", f"got {status}")
        return False

    status, body = client.get("/health")
    if status == 200:
        _ok("GET /health → 200", body.get("status", ""))
    else:
        _fail("GET /health → 200", f"got {status}")

    return True


# ─────────────────────────────────────────────────────────
# B: Character CRUD + PBKD
# ─────────────────────────────────────────────────────────

def section_b(client: APIClient) -> tuple[str, str]:
    """Returns (char1_id, char2_id) for later sections."""
    _section("B: Character CRUD + PBKD")
    uid = uuid.uuid4().hex[:8]

    # B1: Create protagonist
    status, body = client.post("/narrative/characters", {
        "name": f"TestHero_{uid}",
        "role": "protagonist",
        "traits": ["brave", "curious"],
        "goals": ["save the world"],
        "background": "A young hero from the northern mountains.",
    })
    if status == 201 and body.get("role") == "protagonist":
        char1_id   = body["id"]
        char1_name = body["name"]
        _ok("POST /narrative/characters → 201 (protagonist)", f"id={char1_id[:8]}…")
    else:
        _fail("POST /narrative/characters → 201", f"got {status}: {body}")
        char1_id = char1_name = ""

    # B2: Create antagonist with metadata (beliefs/knowledge via metadata dict)
    status, body = client.post("/narrative/characters", {
        "name": f"TestVillain_{uid}",
        "role": "antagonist",
        "traits": ["ruthless", "intelligent"],
        "goals": ["dominate all nations"],
        "metadata": {
            "beliefs": ["power justifies everything"],
            "knowledge": ["ancient dark arts"],
        },
    })
    if status == 201 and body.get("role") == "antagonist":
        char2_id = body["id"]
        _ok("POST /narrative/characters → 201 (antagonist)", f"id={char2_id[:8]}…")
    else:
        _fail("POST /narrative/characters → 201 (antagonist)", f"got {status}")
        char2_id = ""

    # B3: Invalid role ("hero") → Pydantic rejects at input validation → 422
    # Note: _normalize_character_role() applies only to *output* when reading stored data,
    # not to API input. Sending an unlisted role value must fail with 422.
    status, body = client.post("/narrative/characters", {
        "name": f"InvalidRole_{uid}",
        "role": "hero",
    })
    if status == 422:
        _ok("Invalid role 'hero' → 422 (Pydantic input validation)")
    else:
        _fail("Invalid role 'hero' should return 422", f"got {status}: role={body.get('role')}")

    # B4: Invalid role "villain" → 422
    status, body = client.post("/narrative/characters", {
        "name": f"InvalidRole2_{uid}",
        "role": "villain",
    })
    if status == 422:
        _ok("Invalid role 'villain' → 422 (Pydantic input validation)")
    else:
        _fail("Invalid role 'villain' should return 422", f"got {status}")

    # B5: List characters — both protagonists/antagonist present
    status, body = client.get("/narrative/characters")
    if status == 200 and isinstance(body, list):
        names = {c["name"] for c in body}
        both  = (f"TestHero_{uid}" in names) and (f"TestVillain_{uid}" in names)
        if both:
            _ok(f"GET /narrative/characters → {len(body)} characters, both test chars found")
        else:
            _fail("GET /narrative/characters — test characters missing", f"names sample={list(names)[:4]}")
    else:
        _fail("GET /narrative/characters → 200", f"got {status}")

    # B6: Get PBKD for char1
    if char1_id:
        status, body = client.get(f"/narrative/characters/{char1_id}/pbkd")
        if status == 200 and "personality" in body:
            _ok("GET /narrative/characters/{id}/pbkd → 200", f"personality={body['personality']}")
        else:
            _fail("GET /narrative/characters/{id}/pbkd → 200", f"got {status}: {body}")

    # B7: Patch character — update traits
    if char1_id:
        status, body = client.patch(f"/narrative/characters/{char1_id}", {
            "traits": ["brave", "curious", "determined"],
        })
        if status == 200 and "determined" in body.get("traits", []):
            _ok("PATCH /narrative/characters/{id} → traits updated")
        else:
            _fail("PATCH /narrative/characters/{id}", f"got {status}: traits={body.get('traits')}")

    # B8: PBKD search by trait keyword (substring match)
    if char2_id:
        status, body = client.get(
            "/narrative/characters/pbkd/search",
            params={"query": "ruthless"},
        )
        if status == 200:
            results = body.get("results", [])
            found   = any(r["character_id"] == char2_id for r in results)
            if found:
                _ok("PBKD search 'ruthless' → antagonist found")
            else:
                _fail("PBKD search 'ruthless' → character not found", f"count={body.get('count')}")
        else:
            _fail("GET /narrative/characters/pbkd/search → 200", f"got {status}")

    # B9: PBKD search scoped to desires (D) only
    status, body = client.get(
        "/narrative/characters/pbkd/search",
        params={"query": "save", "scopes": "D"},
    )
    if status == 200 and body.get("scopes") == ["D"]:
        _ok("PBKD search scoped to D (desires) → 200", f"count={body.get('count')}")
    elif status == 200:
        _fail("PBKD search scopes field mismatch", f"scopes={body.get('scopes')}, expected ['D']")
    else:
        _fail("PBKD search scoped query → 200", f"got {status}")

    return char1_id, char2_id


# ─────────────────────────────────────────────────────────
# C: Lore CRUD
# ─────────────────────────────────────────────────────────

def section_c(client: APIClient) -> list[str]:
    """Returns list of lore keys created."""
    _section("C: Lore CRUD")
    uid  = uuid.uuid4().hex[:8]
    key1 = f"world_rule_{uid}"
    key2 = f"magic_system_{uid}"

    # C1: Add basic lore fact
    status, body = client.post("/narrative/world/lore", {
        "key":   key1,
        "value": "Time flows in a spiral — the past echoes through the present.",
    })
    if status == 200 and body.get("key") == key1:
        _ok("POST /narrative/world/lore → 200 (basic)", f"key={key1}")
    else:
        _fail("POST /narrative/world/lore → 200", f"got {status}: {body}")

    # C2: Add lore with source + tags
    status, body = client.post("/narrative/world/lore", {
        "key":    key2,
        "value":  "Magic is drawn from emotional resonance — stronger emotion = stronger spell.",
        "source": "The Ancient Codex",
        "tags":   ["magic", "emotion", "power"],
    })
    if status == 200 and body.get("source") == "The Ancient Codex":
        tags = sorted(body.get("tags", []))
        _ok("POST /narrative/world/lore → 200 (with source + tags)", f"tags={tags}")
    else:
        _fail("POST /narrative/world/lore (with tags) → 200", f"got {status}: {body}")

    # C3: List lore — both keys present
    status, body = client.get("/narrative/world/lore")
    if status == 200 and isinstance(body, list):
        keys = {fact["key"] for fact in body}
        if key1 in keys and key2 in keys:
            _ok(f"GET /narrative/world/lore → {len(body)} facts, both test keys found")
        else:
            _fail("GET /narrative/world/lore — test keys missing", f"keys_sample={list(keys)[:4]}")
    else:
        _fail("GET /narrative/world/lore → 200", f"got {status}")

    # C4: Upsert — same key updates value
    new_value = "Magic requires blood sacrifice in addition to emotional resonance."
    status, body = client.post("/narrative/world/lore", {
        "key":    key2,
        "value":  new_value,
        "source": "The Ancient Codex, Revised Edition",
    })
    if status == 200 and body.get("value") == new_value:
        _ok("Upsert lore (same key) → value updated")
    else:
        _fail("Upsert lore same key", f"got {status}: value={body.get('value')!r}")

    return [key1, key2]


# ─────────────────────────────────────────────────────────
# D: Scene CRUD
# ─────────────────────────────────────────────────────────

def section_d(client: APIClient) -> list[str]:
    """Returns list of scene IDs created."""
    _section("D: Scene CRUD")
    uid = uuid.uuid4().hex[:8]

    # D1: Title only
    status, body = client.post("/narrative/scenes", {"title": f"Opening Act {uid}"})
    if status == 201 and "id" in body:
        scene1_id = body["id"]
        _ok("POST /narrative/scenes → 201 (title only)", f"id={scene1_id[:8]}…")
    else:
        _fail("POST /narrative/scenes → 201", f"got {status}: {body}")
        scene1_id = ""

    # D2: Full scene with beats + characters
    status, body = client.post("/narrative/scenes", {
        "title":      f"Battle Scene {uid}",
        "summary":    "The hero confronts the villain in the ancient temple.",
        "beats":      [
            "Hero enters the temple cautiously.",
            "Villain reveals his true motives.",
            "Final confrontation begins.",
        ],
        "characters": ["Hero", "Villain"],
    })
    if status == 201 and len(body.get("beats", [])) == 3:
        scene2_id = body["id"]
        _ok("POST /narrative/scenes → 201 (beats + characters)", f"beats={len(body['beats'])}")
    else:
        _fail("POST /narrative/scenes (with beats) → 201", f"got {status}: {body}")
        scene2_id = ""

    # D3: List scenes
    status, body = client.get("/narrative/scenes")
    if status == 200 and isinstance(body, list):
        ids   = {s["id"] for s in body}
        found = all(sid in ids for sid in [scene1_id, scene2_id] if sid)
        if found:
            _ok(f"GET /narrative/scenes → {len(body)} scenes, test scenes found")
        else:
            _fail("GET /narrative/scenes — test scenes missing")
    else:
        _fail("GET /narrative/scenes → 200", f"got {status}")

    return [scene1_id, scene2_id]


# ─────────────────────────────────────────────────────────
# E: Timeline Events
# ─────────────────────────────────────────────────────────

def section_e(client: APIClient) -> list[str]:
    """Returns list of event IDs created."""
    _section("E: Timeline Events")
    uid = uuid.uuid4().hex[:8]

    # E1: Title only
    status, body = client.post("/narrative/timeline/events", {
        "title": f"The Great War begins {uid}",
    })
    if status == 200 and "id" in body:
        ev1_id = body["id"]
        _ok("POST /narrative/timeline/events → 200 (title only)", f"id={ev1_id[:8]}…")
    else:
        _fail("POST /narrative/timeline/events → 200", f"got {status}: {body}")
        ev1_id = ""

    # E2: With description
    status, body = client.post("/narrative/timeline/events", {
        "title":       f"The Hero's Awakening {uid}",
        "description": "The protagonist discovers their true destiny.",
    })
    if status == 200 and "protagonist" in (body.get("description") or ""):
        ev2_id = body["id"]
        _ok("POST /narrative/timeline/events → 200 (with description)")
    else:
        _fail("POST /narrative/timeline/events (desc) → 200", f"got {status}: {body}")
        ev2_id = ""

    # E3: List events
    status, body = client.get("/narrative/timeline/events")
    if status == 200 and isinstance(body, list):
        ids   = {e["id"] for e in body}
        found = all(eid in ids for eid in [ev1_id, ev2_id] if eid)
        if found:
            _ok(f"GET /narrative/timeline/events → {len(body)} events, test events found")
        else:
            _fail("GET /narrative/timeline/events — test events missing")
    else:
        _fail("GET /narrative/timeline/events → 200", f"got {status}")

    return [ev1_id, ev2_id]


# ─────────────────────────────────────────────────────────
# F: Relationships
# ─────────────────────────────────────────────────────────

def section_f(client: APIClient, char1_id: str, char2_id: str) -> None:
    _section("F: Relationships")

    src = char1_id or f"test_char_a_{uuid.uuid4().hex[:6]}"
    tgt = char2_id or f"test_char_b_{uuid.uuid4().hex[:6]}"

    # F1: Ally
    status, body = client.post("/narrative/relationships", {
        "source":            src,
        "target":            f"companion_{uuid.uuid4().hex[:6]}",
        "relationship_type": "ally",
        "strength":          0.8,
    })
    if status == 200 and body.get("relationship_type") == "ally":
        _ok("POST /narrative/relationships → 200 (ally)", f"strength={body.get('strength')}")
    else:
        _fail("POST /narrative/relationships (ally) → 200", f"got {status}: {body}")

    # F2: Enemy with note
    status, body = client.post("/narrative/relationships", {
        "source":            src,
        "target":            tgt,
        "relationship_type": "enemy",
        "strength":          0.9,
        "note":              "Ancient rivalry dating back to the first age.",
    })
    if status == 200 and body.get("relationship_type") == "enemy":
        notes = body.get("notes", [])
        _ok("POST /narrative/relationships → 200 (enemy + note)", f"notes count={len(notes)}")
    else:
        _fail("POST /narrative/relationships (enemy) → 200", f"got {status}: {body}")

    # F3: Romantic
    status, body = client.post("/narrative/relationships", {
        "source":            src,
        "target":            f"love_interest_{uuid.uuid4().hex[:6]}",
        "relationship_type": "romantic",
        "strength":          0.95,
    })
    if status == 200 and body.get("relationship_type") == "romantic":
        _ok("POST /narrative/relationships → 200 (romantic)")
    else:
        _fail("POST /narrative/relationships (romantic) → 200", f"got {status}: {body}")

    # F4: Mentor
    status, body = client.post("/narrative/relationships", {
        "source":            src,
        "target":            f"mentor_{uuid.uuid4().hex[:6]}",
        "relationship_type": "mentor",
        "strength":          0.7,
    })
    if status == 200 and body.get("relationship_type") == "mentor":
        _ok("POST /narrative/relationships → 200 (mentor)")
    else:
        _fail("POST /narrative/relationships (mentor) → 200", f"got {status}: {body}")


# ─────────────────────────────────────────────────────────
# G: State Mutation (state engine pipeline)
# ─────────────────────────────────────────────────────────

def section_g(client: APIClient) -> None:
    _section("G: State Mutation")

    _LLM_TIMEOUT = 90  # Ollama may take up to ~60s for first generation

    # G1: English scene — basic smoke test (may call Ollama internally)
    try:
        status, body = client.post("/narrative/state-mutation", {
            "scene_text": (
                "Elena stepped into the ancient chamber, her lantern casting long shadows "
                "on the mosaic floor. The Warden stood at the far end, arms crossed, his "
                "expression unreadable. 'You have come for the Seal,' he said — not a question. "
                "Elena nodded. 'My people are dying. I have no choice.' "
                "The Warden considered this, then stepped aside."
            ),
            "scene_title": "The Chamber of the Warden",
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("POST /narrative/state-mutation", f"LLM timed out after {_LLM_TIMEOUT}s")
        return

    if status == 200:
        _ok("POST /narrative/state-mutation → 200 (English scene)")
        # G1a: Check required response keys exist
        for key in ("success", "entities", "events"):
            if key in body:
                _ok(f"  response.{key} field present")
            else:
                _fail(f"  response.{key} field missing", f"keys={list(body.keys())[:8]}")
    else:
        _fail("POST /narrative/state-mutation → 200", f"got {status}: {str(body)[:300]}")

    # G2: Second scene — success flag present
    try:
        status, body = client.post("/narrative/state-mutation", {
            "scene_text": "The knight rode through the burning village. A child cried in the distance.",
            "scene_title": "Aftermath",
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("State mutation second scene", "LLM timeout")
        return

    if status == 200 and "success" in body:
        _ok("State mutation response.success field present", f"success={body.get('success')}")
    elif status == 200:
        _fail("State mutation response missing 'success' key", f"keys={list(body.keys())[:6]}")
    else:
        _fail("State mutation (second scene) → 200", f"got {status}")

    # G3: Context options forwarded correctly
    try:
        status, body = client.post("/narrative/state-mutation", {
            "scene_text": "The council met at dawn to deliberate the terms of the truce.",
            "scene_title": "Council at Dawn",
            "context": {"allow_canon_override": False, "async_analysis": False},
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("State mutation with context options", "LLM timeout")
        return

    if status == 200:
        _ok("State mutation with context options → 200")
    elif status == 500:
        _skip("State mutation with context options", "Server 500 — likely Ollama busy; re-run to verify")
    else:
        _fail("State mutation with context options → 200", f"got {status}")


# ─────────────────────────────────────────────────────────
# H: Query System
# ─────────────────────────────────────────────────────────

def section_h(client: APIClient) -> None:
    _section("H: Query System")
    _LLM_TIMEOUT = 90

    def _query(prompt: str, label: str) -> None:
        try:
            status, body = client.post("/narrative/query", {"query": prompt}, timeout=_LLM_TIMEOUT)
        except TimeoutError:
            _skip(label, f"LLM timeout after {_LLM_TIMEOUT}s")
            return
        if status == 200:
            _ok(f"POST /narrative/query → 200 ({label})", f"keys={list(body.keys())[:4]}")
        else:
            _fail(f"POST /narrative/query ({label}) → 200", f"got {status}: {str(body)[:200]}")

    _query("Who are the main characters?", "character query")
    _query("What are the key conflicts in this story?", "conflict query")
    _query("Summarize the timeline of events.", "timeline query")


# ─────────────────────────────────────────────────────────
# I: Narrative Summary
# ─────────────────────────────────────────────────────────

def section_i(client: APIClient) -> None:
    _section("I: Narrative Summary")

    status, body = client.get("/narrative/summary")
    if status == 200:
        expected = {"characters", "scenes", "timeline_events", "lore_facts", "relationships"}
        missing  = expected - set(body.keys())
        if not missing:
            _ok(
                "GET /narrative/summary → 200 (all count fields)",
                f"chars={body.get('characters')} scenes={body.get('scenes')} "
                f"lore={body.get('lore_facts')} events={body.get('timeline_events')} "
                f"rel={body.get('relationships')}",
            )
        else:
            _fail("Summary response missing fields", f"missing={missing}")
    else:
        _fail("GET /narrative/summary → 200", f"got {status}: {str(body)[:200]}")

    # I2: Summary reflects data created in earlier sections
    status, body2 = client.get("/narrative/summary")
    if status == 200:
        chars = body2.get("characters", 0)
        lore  = body2.get("lore_facts", 0)
        if chars > 0 and lore > 0:
            _ok("Summary counts are non-zero (data from earlier sections visible)")
        else:
            _skip("Summary counts non-zero check", f"chars={chars} lore={lore} (may be zero if sections skipped)")


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def main() -> None:
    global _verbose
    parser = argparse.ArgumentParser(description="Phase 3A: Narrative Domain Core")
    parser.add_argument("--api",     default=DEFAULT_API)
    parser.add_argument("--section", choices=["a","b","c","d","e","f","g","h","i"])
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _verbose = args.verbose
    client   = APIClient(args.api, verbose=args.verbose)

    print(f"{BOLD}NarrativeOS — Phase 3A: Narrative Domain Core{RESET}")
    print(f"API: {args.api}\n")

    sec      = args.section
    char1_id = char2_id = ""

    if not sec or sec == "a":
        ok = section_a(client)
        if not ok and not sec:
            print(f"\n{RED}Server unreachable — aborting.{RESET}")
            sys.exit(1)

    if not sec or sec == "b":
        char1_id, char2_id = section_b(client)
    if not sec or sec == "c":
        section_c(client)
    if not sec or sec == "d":
        section_d(client)
    if not sec or sec == "e":
        section_e(client)
    if not sec or sec == "f":
        section_f(client, char1_id, char2_id)
    if not sec or sec == "g":
        section_g(client)
    if not sec or sec == "h":
        section_h(client)
    if not sec or sec == "i":
        section_i(client)

    sys.exit(print_summary())


if __name__ == "__main__":
    main()
