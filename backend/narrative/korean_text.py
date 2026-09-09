from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")

_KOREAN_NORMALIZATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b미친는\b"), "미친"),
    (re.compile(r"\b미친\s+는\b"), "미친"),
    (re.compile(r"\b이상한\s+성격\b"), "성격이 이상한"),
    (re.compile(r"\b성격\s+이상한\b"), "성격이 이상한"),
    (re.compile(r"\b사람\s+이다\b"), "사람"),
]

_KOREAN_CHARACTER_QUERY_PATTERNS: list[re.Pattern[str]] = [
    # Possessive: "X의 계획/신념/..." — check first so "X의 신념은 뭔가?" extracts X, not "신념"
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]{2,6})\s*의\s*(계획|생각|목표|역할|상태|현재|미래|과거|행동|관계|신념|욕망|기억)"),
    # Identity/personality queries
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*어떤\s*사람"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(의)?\s*성격"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*어때"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*누구야"),
    # "X은/는 지금/현재/어디 ...?" action/state queries
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]{2,6})\s*(은|는|이|가)\s+(지금|현재|앞으로|어디|언제|왜|어떻게|어떤)"),
    # Generic subject at start of sentence — fallback, anchored to ^ to avoid false positives
    re.compile(r"^(?P<name>[가-힣]{2,6})\s*(은|는|이|가)\s+"),
]

_KO_TOPIC_PARTICLE = re.compile(r"(은|는|이|가)$")

# Narrower patterns used ONLY for character_profile routing — identity/personality queries.
# Action/state queries ("X은 지금 무엇을...") intentionally excluded so they fall through
# to semantic_query where they get rich narrative memory results.
_KOREAN_IDENTITY_QUERY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*어떤\s*사람"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(의)?\s*성격"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*어때"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*누구야"),
    # "X는 누구인가?" — only when X is at the START of the sentence (anchored)
    # to avoid matching "...인물은 누구인가?" where 인물 is a generic noun
    re.compile(r"^(?P<name>[가-힣A-Za-z0-9_]{2,6})\s*(은|는|이|가)?\s*누구인가"),
]

# Generic Korean nouns that look like character names but are NOT
_KOREAN_GENERIC_NOUNS = frozenset({
    "인물", "사람", "캐릭터", "존재", "누구", "상대", "인간", "등장인물",
    "적", "동료", "친구", "가족", "부하", "주인공", "상대방",
})

# Relationship/trust/alliance queries — route to semantic_query (uses KG context)
_KOREAN_RELATIONSHIP_QUERY_PATTERNS: list[re.Pattern[str]] = [
    # "X가 가장 신뢰할/믿을/가까운 인물은?"
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]{2,6})\s*(은|는|이|가)\s+가장\s+(?:신뢰|믿|좋아|가까운|친한|믿을)"),
    # "X는 누구를 신뢰/믿는가?"
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]{2,6})\s*(은|는|이|가)\s+누구를?\s+(?:신뢰|믿)"),
    # "X의 동맹/신뢰/적대 관계는?"
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]{2,6})\s*의\s*(?:동맹|신뢰|관계|동료|적대|갈등)"),
    # "X와 가장 관계가 깊은/좋은/나쁜 인물은?"
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]{2,6})\s*(?:와|과)\s+(?:가장|제일)\s+(?:관계|친한|가까운)"),
]


def normalize_korean_text(text: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", text).strip()
    for pattern, replacement in _KOREAN_NORMALIZATION_RULES:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def extract_character_query_name(query: str) -> str | None:
    compact = normalize_korean_text(query)
    for pattern in _KOREAN_CHARACTER_QUERY_PATTERNS:
        match = pattern.search(compact)
        if match:
            name = match.group("name")
            # Strip trailing topic/subject particles that were absorbed into the name group
            name = _KO_TOPIC_PARTICLE.sub("", name)
            if len(name) >= 2:
                return name
    return None


def extract_character_identity_query_name(query: str) -> str | None:
    """Like extract_character_query_name but only matches identity/personality queries.
    Action queries ("X은 지금 무엇을...") are intentionally excluded so they reach semantic_query.
    Generic nouns (인물, 사람, ...) are rejected even when pattern matches."""
    compact = normalize_korean_text(query)
    for pattern in _KOREAN_IDENTITY_QUERY_PATTERNS:
        match = pattern.search(compact)
        if match:
            name = match.group("name")
            name = _KO_TOPIC_PARTICLE.sub("", name)
            if len(name) >= 2 and name not in _KOREAN_GENERIC_NOUNS:
                return name
    return None


def extract_relationship_query_name(query: str) -> str | None:
    """Extract character name from relationship/trust queries.
    e.g. '카엘은 가장 신뢰할 가능성이 높은 인물은 누구인가?' → '카엘'"""
    compact = normalize_korean_text(query)
    for pattern in _KOREAN_RELATIONSHIP_QUERY_PATTERNS:
        match = pattern.search(compact)
        if match:
            name = match.group("name")
            name = _KO_TOPIC_PARTICLE.sub("", name)
            if len(name) >= 2 and name not in _KOREAN_GENERIC_NOUNS:
                return name
    return None