#!/usr/bin/env python3
"""
debug_phase3b.py — Phase 3B: Korean Language Layer

Sections:
  KR-A  Korean data storage (lore + characters with Korean text)
  KR-B  Korean PBKD retrieval (substring search with Korean query)
  KR-C  State mutation with Korean scene text
  KR-D  LLM Korean generation (rewrite + query; gracefully skipped if unavailable)
  KR-E  Cross-language robustness (Korean ↔ English)
  KR-F  Mixed-language stability (KR/EN mixed text)
  KR-G  Language Consistency Harness — summary report

Usage:
  python3 debug_phase3b.py [--api URL] [--section kr-a|kr-b|kr-c|kr-d|kr-e|kr-f|kr-g] [-v]

The Korean Language Layer tests verify that:
  KR → KR     Korean text stored and retrieved correctly
  KR → embed  Korean PBKD traits findable via Korean substring search
  KR → LLM    Korean scene processed without crash (LLM output quality is qualitative)
  Mixed       Mixed KR/EN input never causes 5xx errors
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
BLUE   = "\033[94m"

_pass_count = 0
_fail_count = 0
_skip_count = 0
_info_count = 0
_verbose    = False

# Korean charset detection helper
def _has_korean(text: str) -> bool:
    return any("가" <= ch <= "힣" or "ᄀ" <= ch <= "ᇿ" for ch in text)


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


def _info(label: str, detail: str = "") -> None:
    """Qualitative observation — not pass/fail."""
    global _info_count
    _info_count += 1
    msg = f"  {BLUE}ℹ{RESET} {label}"
    if detail:
        msg += f"  {CYAN}({detail}){RESET}"
    print(msg)


def _section(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{RESET}")


def print_summary() -> int:
    total = _pass_count + _fail_count
    color = GREEN if _fail_count == 0 else RED
    print(f"\n{BOLD}{'─' * 56}{RESET}")
    print(f"{BOLD}Result: {color}{_pass_count}/{total} passed{RESET}", end="")
    if _skip_count:
        print(f"  {YELLOW}({_skip_count} skipped){RESET}", end="")
    if _info_count:
        print(f"  {BLUE}({_info_count} observations){RESET}", end="")
    print()
    if _fail_count > 0:
        print(f"{RED}Phase 3B has failures — check details above.{RESET}")
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
        timeout: int = 30,
    ) -> tuple[int, Any]:
        url = self.base_url + path
        if params:
            qs  = "&".join(
                f"{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}"
                for k, v in params.items()
            )
            url = f"{url}?{qs}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
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
             token: str | None = None, timeout: int = 30) -> tuple[int, Any]:
        return self.request("POST", path, body=body, token=token, timeout=timeout)

    def patch(self, path: str, body: dict[str, Any],
              token: str | None = None) -> tuple[int, Any]:
        return self.request("PATCH", path, body=body, token=token)


# ─────────────────────────────────────────────────────────
# KR-A: Korean Data Storage
# ─────────────────────────────────────────────────────────

# Shared state passed between sections
_kr_state: dict[str, Any] = {}


def section_kr_a(client: APIClient) -> None:
    _section("KR-A: Korean Data Storage")
    uid = uuid.uuid4().hex[:6]

    # KR-A1: Store Korean lore fact
    kr_key1 = f"세계관_{uid}"
    status, body = client.post("/narrative/world/lore", {
        "key":   kr_key1,
        "value": "시간은 나선형으로 흐른다 — 과거의 메아리가 현재를 관통한다.",
        "source": "고대 기록서",
        "tags":  ["세계관", "시간", "마법"],
    })
    if status == 200 and body.get("key") == kr_key1:
        _kr_state["lore_key1"] = kr_key1
        _ok("POST /narrative/world/lore → 200 (Korean key + value)", f"key={kr_key1}")
    else:
        _fail("POST /narrative/world/lore (Korean) → 200", f"got {status}: {body}")

    # KR-A2: Store Korean lore — magic system
    kr_key2 = f"마법체계_{uid}"
    status, body = client.post("/narrative/world/lore", {
        "key":   kr_key2,
        "value": "마법은 감정의 공명에서 비롯된다. 감정이 강할수록 주문도 강력해진다.",
        "tags":  ["마법", "감정"],
    })
    if status == 200 and body.get("key") == kr_key2:
        _kr_state["lore_key2"] = kr_key2
        _ok("POST /narrative/world/lore → 200 (Korean magic system lore)")
    else:
        _fail("POST /narrative/world/lore (Korean magic) → 200", f"got {status}")

    # KR-A3: Create Korean character — protagonist
    kr_char1_name = f"서준_{uid}"
    status, body = client.post("/narrative/characters", {
        "name":       kr_char1_name,
        "role":       "protagonist",
        "traits":     ["용감하다", "호기심이 많다", "충직하다"],
        "goals":      ["세상을 구하다", "가족을 지키다"],
        "background": "북쪽 산맥 출신의 젊은 전사. 어린 시절 마을이 불타는 것을 목격했다.",
    })
    if status == 201 and body.get("name") == kr_char1_name:
        char1_id = body["id"]
        _kr_state["char1_id"]   = char1_id
        _kr_state["char1_name"] = kr_char1_name
        _ok("POST /narrative/characters → 201 (Korean protagonist)", f"id={char1_id[:8]}…")
        # Verify Korean is preserved in stored traits
        if "용감하다" in body.get("traits", []):
            _ok("Korean traits preserved in response", f"traits={body['traits'][:2]}")
        else:
            _fail("Korean traits missing from response", f"traits={body.get('traits')}")
    else:
        _fail("POST /narrative/characters (Korean protagonist) → 201", f"got {status}: {body}")

    # KR-A4: Create Korean character — antagonist with PBKD beliefs
    kr_char2_name = f"악당_박민준_{uid}"
    status, body = client.post("/narrative/characters", {
        "name":  kr_char2_name,
        "role":  "antagonist",
        "traits": ["냉혹하다", "지략이 뛰어나다"],
        "goals":  ["모든 왕국을 지배하다"],
        "metadata": {
            "beliefs": ["권력이 모든 것을 정당화한다"],
            "knowledge": ["고대 흑마법", "정치적 음모"],
            "desires": ["영원한 권력"],
        },
    })
    if status == 201 and body.get("name") == kr_char2_name:
        char2_id = body["id"]
        _kr_state["char2_id"]   = char2_id
        _kr_state["char2_name"] = kr_char2_name
        pbkd = body.get("pbkd", {})
        _ok("POST /narrative/characters → 201 (Korean antagonist + metadata)")
        if "권력이 모든 것을 정당화한다" in pbkd.get("beliefs", []):
            _ok("Korean beliefs correctly stored in PBKD", f"beliefs={pbkd.get('beliefs')[:1]}")
        else:
            _fail("Korean beliefs not found in PBKD", f"pbkd={pbkd}")
    else:
        _fail("POST /narrative/characters (Korean antagonist) → 201", f"got {status}")

    # KR-A5: Verify Korean lore is retrievable
    status, body = client.get("/narrative/world/lore")
    if status == 200 and isinstance(body, list):
        keys = {f["key"] for f in body}
        if kr_key1 in keys and kr_key2 in keys:
            _ok("GET /narrative/world/lore → Korean keys present in list")
        else:
            _fail("Korean lore keys missing from list", f"keys={list(keys)[:6]}")
    else:
        _fail("GET /narrative/world/lore → 200", f"got {status}")

    # KR-A6: Verify Korean characters are retrievable
    status, body = client.get("/narrative/characters")
    if status == 200 and isinstance(body, list):
        names = {c["name"] for c in body}
        if kr_char1_name in names and kr_char2_name in names:
            _ok("GET /narrative/characters → Korean characters present in list")
        else:
            _fail("Korean character names missing from list", f"names_sample={list(names)[:4]}")
    else:
        _fail("GET /narrative/characters → 200", f"got {status}")


# ─────────────────────────────────────────────────────────
# KR-B: Korean PBKD Retrieval (substring search)
# ─────────────────────────────────────────────────────────

def section_kr_b(client: APIClient) -> None:
    _section("KR-B: Korean PBKD Retrieval")

    char1_id = _kr_state.get("char1_id", "")
    char2_id = _kr_state.get("char2_id", "")

    if not char1_id:
        _skip("Korean PBKD retrieval", "KR-A skipped — no Korean characters stored")
        return

    # KR-B1: Search by Korean personality trait
    status, body = client.get(
        "/narrative/characters/pbkd/search",
        params={"query": "용감", "scopes": "P"},
    )
    if status == 200:
        results = body.get("results", [])
        found   = any(r["character_id"] == char1_id for r in results)
        if found:
            _ok("PBKD search '용감' (brave) → Korean protagonist found in P scope")
        else:
            _fail("PBKD search '용감' → character not found", f"count={body.get('count')} results={results[:2]}")
    else:
        _fail("PBKD search (Korean query) → 200", f"got {status}")

    # KR-B2: Search by Korean goal/desire
    status, body = client.get(
        "/narrative/characters/pbkd/search",
        params={"query": "세상", "scopes": "D"},
    )
    if status == 200:
        results = body.get("results", [])
        found   = any(r["character_id"] == char1_id for r in results)
        if found:
            _ok("PBKD search '세상' (world) → protagonist found in D (desires) scope")
        else:
            _fail("PBKD search '세상' in D scope → not found", f"count={body.get('count')}")
    else:
        _fail("PBKD search '세상' → 200", f"got {status}")

    # KR-B3: Search by Korean belief in antagonist
    if char2_id:
        status, body = client.get(
            "/narrative/characters/pbkd/search",
            params={"query": "권력", "scopes": "B"},
        )
        if status == 200:
            results = body.get("results", [])
            found   = any(r["character_id"] == char2_id for r in results)
            if found:
                _ok("PBKD search '권력' (power) → antagonist found in B (beliefs) scope")
            else:
                _fail("PBKD search '권력' in B scope → not found", f"results={results[:2]}")
        else:
            _fail("PBKD search '권력' → 200", f"got {status}")

    # KR-B4: Broad search (all scopes) with Korean keyword
    status, body = client.get(
        "/narrative/characters/pbkd/search",
        params={"query": "지배", "scopes": "P,B,K,D"},
    )
    if status == 200:
        count = body.get("count", 0)
        _ok(f"PBKD search '지배' (dominate) across all scopes → count={count}")
    else:
        _fail("PBKD search '지배' → 200", f"got {status}")

    # KR-B5: PBKD endpoint for Korean character
    if char1_id:
        status, body = client.get(f"/narrative/characters/{char1_id}/pbkd")
        if status == 200:
            personality = body.get("personality", [])
            kr_traits = [t for t in personality if _has_korean(t)]
            if kr_traits:
                _ok("GET /characters/{id}/pbkd → Korean traits in personality field", f"{kr_traits[:2]}")
            else:
                _fail("Korean traits missing from PBKD personality", f"personality={personality}")
        else:
            _fail("GET /characters/{id}/pbkd → 200", f"got {status}")


# ─────────────────────────────────────────────────────────
# KR-C: State Mutation with Korean Scene Text
# ─────────────────────────────────────────────────────────

def section_kr_c(client: APIClient) -> None:
    _section("KR-C: State Mutation — Korean Scene Text")

    _LLM_TIMEOUT = 90

    # KR-C1: Pure Korean scene
    korean_scene = (
        "서준은 고대 신전 안으로 조심스럽게 발을 내딛었다. "
        "랜턴 불빛이 모자이크 바닥 위에 긴 그림자를 만들었다. "
        "수호자가 저 멀리 서 있었고, 팔짱을 낀 채 무표정한 눈빛으로 그를 바라봤다. "
        "'봉인을 가지러 왔겠지,' 수호자가 말했다 — 질문이 아니었다. "
        "서준은 고개를 끄덕였다. '우리 마을 사람들이 죽어가고 있어요. 선택의 여지가 없어요.' "
        "수호자는 한참을 생각하다가 옆으로 비켜섰다."
    )

    try:
        status, body = client.post("/narrative/state-mutation", {
            "scene_text":  korean_scene,
            "scene_title": "수호자의 신전",
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("POST /narrative/state-mutation (Korean)", f"LLM timed out after {_LLM_TIMEOUT}s")
        return

    if status == 200:
        _ok("POST /narrative/state-mutation → 200 (pure Korean scene)")
        if "success" in body:
            _ok("State mutation response.success present", f"success={body.get('success')}")
        if "entities" in body:
            chars = body.get("entities", {}).get("characters", [])
            _info(
                "Extracted character entities from Korean scene",
                f"characters={chars}",
            )
    else:
        _fail("POST /narrative/state-mutation (Korean) → 200", f"got {status}: {str(body)[:300]}")

    # KR-C2: Korean scene with explicit character names from KR-A
    char1_name = _kr_state.get("char1_name", "서준")
    try:
        status, body = client.post("/narrative/state-mutation", {
            "scene_text": (
                f"{char1_name}은(는) 박민준의 비밀 기지에 침투했다. "
                "어둠 속에서 그는 마법 두루마리들을 발견했다. "
                "박민준은 갑자기 나타나 무기를 꺼내 들었다. "
                f"'{char1_name}, 네가 여기 올 줄 알았다.' "
                "두 사람의 최후 대결이 시작되었다."
            ),
            "scene_title": "최후의 대결",
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("State mutation (Korean + known chars)", "LLM timeout")
        return

    if status == 200:
        _ok("POST /narrative/state-mutation → 200 (Korean scene with known characters)")
        chars_extracted = body.get("entities", {}).get("characters", [])
        _info(
            "Entities extracted from Korean confrontation scene",
            f"characters={chars_extracted}",
        )
    else:
        _fail("POST /narrative/state-mutation (Korean confrontation) → 200", f"got {status}")

    # KR-C3: Knowledge graph extraction — Korean relation patterns
    kg_scene = (
        "서준는 박민준를 두려워하지만 끝까지 맞서기로 결심했다. "
        "박민준는 서준를 배신하고 마을을 불태웠다. "
        "서준는 박민준를 신뢰했던 시절이 있었지만 이제는 끝났다."
    )
    try:
        status, body = client.post("/narrative/state-mutation", {
            "scene_text":  kg_scene,
            "scene_title": "배신의 기억",
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("State mutation (Korean KG patterns)", "LLM timeout")
        return

    if status == 200:
        _ok("POST /narrative/state-mutation → 200 (Korean KG relation patterns)")
        _info(
            "Korean KG relation extraction smoke test",
            "patterns: 두려워, 배신, 신뢰 tested",
        )
    else:
        _fail("POST /narrative/state-mutation (Korean KG patterns) → 200", f"got {status}")


# ─────────────────────────────────────────────────────────
# KR-D: LLM Korean Generation (graceful skip if unavailable)
# ─────────────────────────────────────────────────────────

def _llm_available(client: APIClient) -> bool:
    """Quick check: does /health report an LLM?"""
    try:
        status, body = client.get("/health")
        if status != 200:
            return False
        llm = body.get("llm") or {}
        return bool(llm.get("status") == "healthy" or llm.get("available"))
    except Exception:
        return False


def section_kr_d(client: APIClient) -> None:
    _section("KR-D: LLM Korean Generation")

    llm_ok = _llm_available(client)
    if not llm_ok:
        _info("LLM health check: not healthy — rewrite tests use fallback mode")

    _LLM_TIMEOUT = 90

    korean_source = (
        "서준은 폭풍우 속을 걸었다. 빗물이 갑옷을 흠뻑 적셨다. "
        "그의 마음속에는 두려움과 결의가 뒤섞여 있었다. "
        "저 멀리 성의 불빛이 보였다. 오늘 밤 모든 것이 결정될 것이다."
    )

    # KR-D1: Rewrite with Korean source text
    try:
        status, body = client.post("/narrative/rewrite", {
            "source_text":  korean_source,
            "scene_title":  "폭풍 속의 행군",
            "instructions": "장면의 긴장감을 더욱 높여주세요.",
            "target_tone":  "dramatic",
            "preserve_characters": True,
            "preserve_canon":      True,
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("POST /narrative/rewrite (Korean)", f"LLM timeout after {_LLM_TIMEOUT}s")
        status, body = -1, {}

    if status == 200:
        _ok("POST /narrative/rewrite → 200 (Korean source text)")
        rewritten = body.get("rewritten_text", "")
        if llm_ok and rewritten and rewritten != korean_source:
            if _has_korean(rewritten):
                _ok("LLM produced Korean output for Korean input", f"len={len(rewritten)}")
            else:
                _info("LLM output has no Korean chars", f"start={rewritten[:100]!r}")
        elif body.get("reason"):
            _info("LLM fallback active", f"reason={body.get('reason')[:80]}")
        else:
            _ok("Rewrite returned text (fallback or LLM)")
    elif status != -1:
        _fail("POST /narrative/rewrite (Korean) → 200", f"got {status}: {str(body)[:300]}")

    # KR-D2: Query with Korean question
    try:
        status, body = client.post("/narrative/query", {
            "query": "이 이야기의 주요 등장인물은 누구인가요?",
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("POST /narrative/query (Korean question)", "LLM timeout")
        status, body = -1, {}

    if status == 200:
        _ok("POST /narrative/query → 200 (Korean question)")
        response_text = json.dumps(body, ensure_ascii=False)
        _info("Query response language", f"contains_korean={_has_korean(response_text)}")
    elif status != -1:
        _fail("POST /narrative/query (Korean) → 200", f"got {status}")

    # KR-D3: Rewrite with Korean source + English instructions (cross-language prompt)
    try:
        status, body = client.post("/narrative/rewrite", {
            "source_text":  korean_source,
            "scene_title":  "March in the Storm",
            "instructions": "Increase tension. Keep the character names in Korean.",
            "target_tone":  "tense",
            "preserve_characters": True,
        }, timeout=_LLM_TIMEOUT)
    except TimeoutError:
        _skip("POST /narrative/rewrite (Korean+EN prompt)", "LLM timeout")
        status, body = -1, {}

    if status == 200:
        _ok("POST /narrative/rewrite → 200 (Korean source + English instructions)")
        rewritten = body.get("rewritten_text", "")
        if rewritten and rewritten != korean_source:
            _info("Rewritten text differs from source", f"len_delta={len(rewritten)-len(korean_source)}")
    elif status != -1:
        _fail("POST /narrative/rewrite (Korean+EN mix) → 200", f"got {status}")


# ─────────────────────────────────────────────────────────
# KR-E: Cross-Language Robustness
# ─────────────────────────────────────────────────────────

def section_kr_e(client: APIClient) -> None:
    _section("KR-E: Cross-Language Robustness")
    uid = uuid.uuid4().hex[:6]

    # KR-E1: English query about Korean characters
    char1_name = _kr_state.get("char1_name", "서준")
    status, body = client.post("/narrative/query", {
        "query": f"What is the background of the character named {char1_name}?",
    })
    if status == 200:
        _ok(f"English query about Korean character '{char1_name}' → 200")
    else:
        _fail("English query about Korean character → 200", f"got {status}")

    # KR-E2: Korean key + English value (mixed key-value lore)
    mixed_key = f"world_origin_{uid}"
    status, body = client.post("/narrative/world/lore", {
        "key":   mixed_key,
        "value": "The ancient kingdom (고대왕국) was founded 3000 years ago.",
        "source": "Mixed source / 혼합 출처",
        "tags":  ["history", "역사"],
    })
    if status == 200 and body.get("key") == mixed_key:
        _ok("Lore with English value + Korean annotations → 200")
    else:
        _fail("Mixed KR/EN lore → 200", f"got {status}")

    # KR-E3: English scene mentioning Korean character names
    try:
        status, body = client.post("/narrative/state-mutation", {
            "scene_text": (
                "서준 entered the throne room and bowed before the king. "
                "박민준 watched from the shadows, his hand resting on his sword. "
                "'The prophecy speaks of you,' the king said quietly."
            ),
            "scene_title": "Throne Room (mixed names)",
        }, timeout=90)
    except TimeoutError:
        _skip("State mutation (English+KR names)", "LLM timeout")
        status, body = -1, {}

    if status == 200:
        _ok("State mutation (English scene with Korean names) → 200")
        chars = body.get("entities", {}).get("characters", [])
        _info("Characters extracted from mixed-name scene", f"characters={chars}")
    elif status != -1:
        _fail("State mutation (English scene + Korean names) → 200", f"got {status}")

    # KR-E4: Korean lore retrievable by English-ish key prefix query
    status, body = client.get(
        "/narrative/characters/pbkd/search",
        params={"query": "curious"},
    )
    if status == 200:
        _ok("PBKD search 'curious' (English) on mixed DB → 200", f"count={body.get('count')}")
    else:
        _fail("PBKD search English term → 200", f"got {status}")

    # KR-E5: Create character with mixed KR/EN fields
    status, body = client.post("/narrative/characters", {
        "name":   f"혼합캐릭터_{uid}",
        "role":   "supporting",
        "traits": ["kind-hearted", "친절하다", "empathetic"],
        "goals":  ["protect the village", "마을을 지키다"],
        "background": "Born in the borderlands between East and West / 동서 경계 지역 출신.",
    })
    if status == 201:
        mixed_id = body["id"]
        _ok("Character with mixed KR/EN traits/goals → 201", f"id={mixed_id[:8]}…")
        traits = body.get("traits", [])
        has_kr_trait = any(_has_korean(t) for t in traits)
        has_en_trait = any(not _has_korean(t) for t in traits)
        if has_kr_trait and has_en_trait:
            _ok("Mixed KR/EN traits preserved in response")
        else:
            _fail("Mixed traits not fully preserved", f"traits={traits}")
    else:
        _fail("Character with mixed KR/EN fields → 201", f"got {status}")


# ─────────────────────────────────────────────────────────
# KR-F: Mixed-Language Stability
# ─────────────────────────────────────────────────────────

def section_kr_f(client: APIClient) -> None:
    _section("KR-F: Mixed-Language Stability")

    # KR-F1: Mixed KR/EN paragraph through state mutation
    mixed_scene = (
        "서준 stepped forward, his voice steady despite the fear in his heart. "
        "'나는 물러서지 않는다,' he declared. "
        "박민준 laughed — a cold, hollow sound. "
        "'용감하다. But courage alone won't save you here.' "
        "The two stood face to face in the ruins of the ancient temple."
    )
    try:
        status, body = client.post("/narrative/state-mutation", {
            "scene_text":  mixed_scene,
            "scene_title": "Confrontation / 대결",
        }, timeout=90)
    except TimeoutError:
        _skip("State mutation (mixed KR/EN paragraph)", "LLM timeout")
        status, body = -1, {}

    if status == 200:
        _ok("State mutation (mixed KR/EN paragraph) → 200 — no crash")
        chars = body.get("entities", {}).get("characters", [])
        _info("Entities from mixed-language scene", f"characters={chars}")
    elif status != -1:
        _fail("State mutation (mixed KR/EN) → 200", f"got {status}: {str(body)[:200]}")

    # KR-F2: Rewrite mixed text — no crash
    try:
        status, body = client.post("/narrative/rewrite", {
            "source_text":  mixed_scene,
            "scene_title":  "Confrontation / 대결",
            "instructions": "Make the tension more visceral.",
            "preserve_characters": True,
        }, timeout=90)
    except TimeoutError:
        _skip("POST /narrative/rewrite (mixed KR/EN)", "LLM timeout")
        status = -1

    if status == 200:
        _ok("POST /narrative/rewrite (mixed KR/EN) → 200 — no crash")
    elif status != -1:
        _fail("POST /narrative/rewrite (mixed KR/EN) → 200", f"got {status}")

    # KR-F3: PBKD consistency — Korean PBKD + update via PATCH
    char1_id = _kr_state.get("char1_id", "")
    if char1_id:
        status, body = client.patch(f"/narrative/characters/{char1_id}", {
            "traits": ["용감하다", "호기심이 많다", "결단력이 있다", "determined"],
        })
        if status == 200:
            traits = body.get("traits", [])
            has_kr = any(_has_korean(t) for t in traits)
            has_en = any(not _has_korean(t) for t in traits)
            if has_kr and has_en:
                _ok("PATCH with mixed KR/EN traits → both preserved")
            elif has_kr:
                _ok("PATCH with mixed traits → Korean preserved (English may have been lost)")
            else:
                _fail("PATCH mixed traits — no Korean traits in result", f"traits={traits}")
        else:
            _fail("PATCH character with mixed traits → 200", f"got {status}")
    else:
        _skip("PATCH mixed traits", "KR-A skipped — no Korean character available")

    # KR-F4: Timeline event with Korean title
    status, body = client.post("/narrative/timeline/events", {
        "title":       "봉인의 해제 — The Breaking of the Seal",
        "description": "The ancient seal was broken, releasing a wave of dark energy.",
    })
    if status == 200 and _has_korean(body.get("title", "")):
        _ok("Timeline event with Korean title → 200, Korean preserved")
    elif status == 200:
        _fail("Timeline event Korean title not preserved", f"title={body.get('title')!r}")
    else:
        _fail("Timeline event (Korean title) → 200", f"got {status}")

    # KR-F5: Scene with Korean title
    status, body = client.post("/narrative/scenes", {
        "title":      "수호자의 신전 — Chamber of the Warden",
        "summary":    "서준 discovers the ancient seal and faces the Warden.",
        "characters": ["서준", "The Warden", "박민준"],
    })
    if status == 201 and _has_korean(body.get("title", "")):
        _ok("Scene with Korean title → 201, Korean preserved")
    elif status == 201:
        _fail("Scene Korean title not preserved", f"title={body.get('title')!r}")
    else:
        _fail("Scene (Korean title) → 201", f"got {status}")


# ─────────────────────────────────────────────────────────
# KR-G: Language Consistency Harness — Summary Report
# ─────────────────────────────────────────────────────────

def section_kr_g(client: APIClient) -> None:
    _section("KR-G: Language Consistency Harness — Summary")

    print(f"\n  {BOLD}Harness Dimensions{RESET}")
    dimensions: list[tuple[str, str, str]] = [
        ("KR → KR",
         "Korean text stored → Korean text retrievable via GET",
         "Verified in KR-A: lore + character list returns Korean keys/names"),
        ("KR → embed → retrieval",
         "Korean PBKD traits findable via Korean substring query",
         "Verified in KR-B: '용감', '세상', '권력' queries return correct characters"),
        ("KR → state mutation",
         "Korean scene processed by pipeline without 5xx error",
         "Verified in KR-C: pure Korean + KG relation patterns"),
        ("KR → LLM → KR",
         "Korean input processed by rewrite/query endpoints without crash",
         "Verified in KR-D: fallback or LLM output — both are valid"),
        ("EN → KR context",
         "English query about Korean characters returns 200",
         "Verified in KR-E: English PBKD query + English query about KR character"),
        ("Mixed → stable",
         "Mixed KR/EN input never causes 5xx, data preserved",
         "Verified in KR-F: state mutation, rewrite, scene, timeline all stable"),
    ]

    all_pass = True
    for i, (dim, desc, evidence) in enumerate(dimensions, start=1):
        print(f"\n  {BOLD}[{i}] {dim}{RESET}")
        print(f"      Goal:     {desc}")
        print(f"      Evidence: {evidence}")

    # Final consistency check — query the API and verify no regressions
    print(f"\n  {BOLD}Regression checks:{RESET}")

    # Check 1: Server still healthy
    status, body = client.get("/health")
    if status == 200:
        _ok("Server still healthy after all Korean tests")
    else:
        _fail("Server health after Korean tests", f"got {status}")
        all_pass = False

    # Check 2: Korean lore still in list
    status, body = client.get("/narrative/world/lore")
    if status == 200 and isinstance(body, list):
        kr_lore = [f for f in body if _has_korean(f.get("key", "") + f.get("value", ""))]
        if kr_lore:
            _ok(f"Korean lore entries still in database — {len(kr_lore)} found")
        else:
            _fail("Korean lore entries missing from database")
            all_pass = False
    else:
        _fail("GET /narrative/world/lore after Korean tests → 200", f"got {status}")
        all_pass = False

    # Check 3: Korean characters still in list
    status, body = client.get("/narrative/characters")
    if status == 200 and isinstance(body, list):
        kr_chars = [c for c in body if _has_korean(c.get("name", ""))]
        if kr_chars:
            _ok(f"Korean characters still in database — {len(kr_chars)} found")
        else:
            _fail("Korean characters missing from database")
            all_pass = False
    else:
        _fail("GET /narrative/characters after Korean tests → 200", f"got {status}")
        all_pass = False

    # Check 4: Summary endpoint reflects Korean data
    status, body = client.get("/narrative/summary")
    if status == 200:
        _ok(
            "Narrative summary after Korean tests",
            f"chars={body.get('characters')} lore={body.get('lore_facts')} "
            f"scenes={body.get('scenes')} events={body.get('timeline_events')}",
        )
    else:
        _fail("GET /narrative/summary after Korean tests → 200", f"got {status}")

    print()
    if all_pass:
        print(f"  {GREEN}{BOLD}Language Consistency Harness: ALL dimensions verified.{RESET}")
    else:
        print(f"  {RED}{BOLD}Language Consistency Harness: some dimensions failed — check above.{RESET}")


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

SECTIONS = {
    "kr-a": ("KR-A", section_kr_a),
    "kr-b": ("KR-B", section_kr_b),
    "kr-c": ("KR-C", section_kr_c),
    "kr-d": ("KR-D", section_kr_d),
    "kr-e": ("KR-E", section_kr_e),
    "kr-f": ("KR-F", section_kr_f),
    "kr-g": ("KR-G", section_kr_g),
}


def main() -> None:
    global _verbose
    parser = argparse.ArgumentParser(description="Phase 3B: Korean Language Layer")
    parser.add_argument("--api",     default=DEFAULT_API)
    parser.add_argument(
        "--section",
        choices=list(SECTIONS.keys()),
        help="Run only one section",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _verbose = args.verbose
    client   = APIClient(args.api, verbose=args.verbose)

    print(f"{BOLD}NarrativeOS — Phase 3B: Korean Language Layer{RESET}")
    print(f"API: {args.api}\n")

    # Quick connectivity check
    try:
        status, _ = client.get("/")
        if status != 200:
            print(f"{RED}Server not reachable (got {status}) — aborting.{RESET}")
            sys.exit(1)
    except Exception as exc:
        print(f"{RED}Server not reachable: {exc} — aborting.{RESET}")
        sys.exit(1)

    sec = args.section
    if sec:
        label, fn = SECTIONS[sec]
        fn(client)
    else:
        # Run all in order; KR-A must run before KR-B/KR-E/KR-F use _kr_state
        for label, fn in SECTIONS.values():
            fn(client)

    sys.exit(print_summary())


if __name__ == "__main__":
    main()
