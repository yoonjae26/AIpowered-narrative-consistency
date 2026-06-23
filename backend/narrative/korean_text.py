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
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*어떤\s*사람"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(의)?\s*성격"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*어때"),
    re.compile(r"(?P<name>[가-힣A-Za-z0-9_]+)\s*(은|는|이|가)?\s*누구야"),
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
            return match.group("name")
    return None