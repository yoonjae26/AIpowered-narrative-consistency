"""
문체 분석기 (Style Analyzer) — Layer 2 Editorial

Layer 1 (Consistency): 캐릭터/타임라인/정전/PBKD 충돌 → 이미 존재
Layer 2 (Editorial):   문체 품질 → 이 모듈

감지 항목:
  REPETITION        - 단어/구문 불필요한 반복
  REPEATED_ACTION   - 동일 행동 동사 반복
  SLOW_PACING       - 극적 진전 없는 단조로운 행동 나열
  WEAK_TRANSITION   - 준비 없는 갑작스러운 전환
  SENTENCE_RHYTHM   - 문장 종결 어미 단조로움
  SHOW_DONT_TELL    - 행동/감각 대신 감정 직접 서술
  (+ LLM 추가 분석: WORDINESS, WEAK_DIALOGUE, DESCRIPTION_DENSITY 등)
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.llm.providers.base import BaseLLMProvider, LLMMessage

# ─── 문장 분리 ────────────────────────────────────────────────────────────────

_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|(?<=[다음])\.\s+")


def _split_sentences(text: str) -> list[str]:
    """마침표/느낌표/물음표 기준으로 한국어 문장 분리."""
    raw = re.split(r"(?<=[.!?。])\s*", text.strip())
    return [s.strip() for s in raw if s.strip()]


# ─── 반복 체크 ────────────────────────────────────────────────────────────────

# 자주 반복되어 문체를 단조롭게 만드는 한국어 부사/접속사
_REPEAT_TARGETS: list[tuple[str, str]] = [
    ("천천히", "slow adverb"),
    ("빠르게", "speed adverb"),
    ("조용히", "quiet adverb"),
    ("갑자기", "sudden adverb"),
    ("부드럽게", "gentle adverb"),
    ("잠시", "pause adverb"),
    ("다시", "again adverb"),
    ("그리고", "conjunction"),
    ("하지만", "conjunction"),
    ("그러나", "conjunction"),
    ("그때", "time marker"),
]

# 동작 동사 패턴 (movement/observation verbs)
_ACTION_VERBS = [
    "걸었다", "걸어갔다", "걸어왔다",
    "달렸다", "뛰었다",
    "멈췄다", "멈추었다",
    "일어났다", "앉았다",
    "바라보았다", "쳐다보았다", "돌아보았다", "바라봤다",
    "나타났다", "등장했다",
    "움직였다", "이동했다",
]
_ACTION_VERB_RE = re.compile("|".join(re.escape(v) for v in _ACTION_VERBS))

# 감정 직접 서술 (show don't tell)
_TELL_VERBS = re.compile(
    r"기뻤다|슬펐다|슬퍼했다|두려웠다|두려워했다|무서웠다|화가 났다|화났다|"
    r"행복했다|불안했다|불안해했다|외로웠다|그리웠다|당황했다|놀랐다|놀라웠다|"
    r"괴로웠다|괴로워했다|답답했다|실망했다"
)

# 갑작스러운 등장 패턴
_ABRUPT_APPEAR_RE = re.compile(r"나타났다|등장했다|모습을 드러냈다")


_MAJOR_TYPES = {"REPETITION", "REPEATED_ACTION", "SLOW_PACING", "WEAK_TRANSITION"}
_MINOR_TYPES = {"SENTENCE_RHYTHM", "WORDINESS", "EXPOSITION", "WEAK_DIALOGUE", "SHOW_DONT_TELL"}


def _severity_for(issue_type: str, confidence: float) -> str:
    if issue_type in _MAJOR_TYPES or confidence >= 0.88:
        return "major"
    if issue_type in _MINOR_TYPES or confidence >= 0.60:
        return "minor"
    return "info"


def _build_issue(
    issue_id: str,
    issue_type: str,
    label_ko: str,
    description: str,
    confidence: float,
    reason: str,
    evidence: list[str],
    suggestion: str,
    replace_hint: str = "",
    with_hint: str = "",
    location: str = "paragraph_1",
) -> dict:
    return {
        "issue_id": issue_id,
        "issue_type": issue_type,
        # 기존 consistency 형식 필드 (패치 파이프라인 호환용)
        "issue": label_ko,
        "type": issue_type.lower(),
        "location": location,
        "severity": "warning",
        "message": description,
        # 프론트엔드 Issue Card 필드
        "description": description,
        "confidence": round(confidence, 3),
        "severity_level": _severity_for(issue_type, confidence),  # "major"|"minor"|"info"
        "reason": reason,
        "evidence": evidence,
        "suggestion": suggestion,
        "replace_hint": replace_hint,
        "with_hint": with_hint,
        "reasoning": [reason],
    }


def _check_repetition(sentences: list[str], text: str) -> list[dict]:
    issues: list[dict] = []
    threshold = 2  # 짧은 텍스트에서는 2회도 반복

    for word, _ in _REPEAT_TARGETS:
        occ = [i for i, s in enumerate(sentences) if word in s]
        if len(occ) >= threshold:
            ev = [sentences[i] for i in occ[:4]]
            loc_nums = [str(i + 1) for i in occ]
            conf = min(0.65 + len(occ) * 0.10, 0.95)
            issues.append(_build_issue(
                issue_id=f"style_rep_{word}",
                issue_type="REPETITION",
                label_ko=f"반복 표현: '{word}'",
                description=f"'{word}'이(가) {len(occ)}번 사용됨 (문장 {', '.join(loc_nums)}).",
                confidence=conf,
                reason=f"'{word}'이(가) 짧은 텍스트에서 {len(occ)}회 반복되어 리듬이 단조로워집니다.",
                evidence=ev,
                suggestion=f"'{word}' 중 일부를 제거하거나 다른 표현으로 대체하여 변화를 주세요.",
                replace_hint=word,
                location=f"sentence_{occ[0]+1}",
            ))

    return issues


def _check_repeated_action(sentences: list[str]) -> list[dict]:
    issues: list[dict] = []
    # 각 문장에서 동작 동사 추출
    verb_occurrences: dict[str, list[int]] = {}
    for i, s in enumerate(sentences):
        for m in _ACTION_VERB_RE.finditer(s):
            verb = m.group(0)
            verb_occurrences.setdefault(verb, []).append(i)

    for verb, indices in verb_occurrences.items():
        if len(indices) < 2:
            continue
        ev = [sentences[i] for i in indices[:4]]
        loc_nums = [str(i + 1) for i in indices]
        conf = min(0.62 + len(indices) * 0.11, 0.93)
        issues.append(_build_issue(
            issue_id=f"style_action_{verb}",
            issue_type="REPEATED_ACTION",
            label_ko=f"행동 반복: '{verb}'",
            description=f"행동 동사 '{verb}'이(가) {len(indices)}번 반복됨 (문장 {', '.join(loc_nums)}).",
            confidence=conf,
            reason=f"'{verb}'이(가) 문장 {', '.join(loc_nums)}에서 반복 사용되어 장면이 정체됩니다.",
            evidence=ev,
            suggestion=f"반복되는 '{verb}' 중 일부를 다른 동작 묘사나 감각적 디테일로 대체하세요.",
            replace_hint=verb,
            location=f"sentence_{indices[0]+1}",
        ))

    return issues


def _check_pacing(sentences: list[str]) -> list[dict]:
    if len(sentences) < 4:
        return []

    # 연속 동작 문장 연속 길이 측정
    consecutive = 0
    max_consecutive = 0
    max_run_start = 0
    run_start = 0

    for i, s in enumerate(sentences):
        if _ACTION_VERB_RE.search(s):
            if consecutive == 0:
                run_start = i
            consecutive += 1
            if consecutive > max_consecutive:
                max_consecutive = consecutive
                max_run_start = run_start
        else:
            consecutive = 0

    if max_consecutive < 3:
        return []

    run_sentences = sentences[max_run_start: max_run_start + max_consecutive]
    conf = min(0.78 + max_consecutive * 0.03, 0.95)
    return [_build_issue(
        issue_id="style_pacing_slow",
        issue_type="SLOW_PACING",
        label_ko="느린 페이싱",
        description=f"연속 {max_consecutive}개 문장이 단조로운 행동(이동/관찰)만 묘사합니다.",
        confidence=conf,
        reason=(
            "장면이 이동·관찰 동사만 반복되어 극적 긴장감이 형성되지 않습니다. "
            "내면 묘사나 감각적 디테일, 대화가 부족합니다."
        ),
        evidence=run_sentences[:4],
        suggestion=(
            "연속 행동 묘사 사이에 캐릭터 내면 독백, 감각적 환경 묘사, "
            "또는 짧은 대화를 삽입하여 페이스를 조절하세요."
        ),
        location=f"sentence_{max_run_start+1}",
    )]


def _check_weak_transition(sentences: list[str]) -> list[dict]:
    issues: list[dict] = []
    for i, s in enumerate(sentences):
        if s.startswith("그때") and _ABRUPT_APPEAR_RE.search(s):
            ctx = [sentences[i - 1]] if i > 0 else []
            issues.append(_build_issue(
                issue_id=f"style_transition_{i}",
                issue_type="WEAK_TRANSITION",
                label_ko="약한 장면 전환",
                description="인물이나 사건이 복선 없이 갑작스럽게 등장합니다.",
                confidence=0.80,
                reason=(
                    "'그때 X가 나타났다' 패턴은 독자에게 전환 신호나 복선을 제공하지 않아 "
                    "몰입을 방해합니다."
                ),
                evidence=ctx + [s],
                suggestion=(
                    "등장 직전에 소리, 그림자, 공기 변화 등의 감각적 복선을 추가하거나 "
                    "전환 문장을 삽입하세요. 예: '나뭇가지 사이로 발소리가 들렸다.'"
                ),
                replace_hint=s,
                location=f"sentence_{i+1}",
            ))
    return issues


def _check_sentence_rhythm(sentences: list[str]) -> list[dict]:
    if len(sentences) < 5:
        return []

    # 문장 종결 어미 추출 (다/었다/았다/했다/겠다)
    ending_re = re.compile(r"([가-힣]{1,4}(?:었다|았다|했다|겠다|는다|ㄴ다|이다|지다))[.\s!?]*$")
    endings: list[str] = []
    for s in sentences:
        m = ending_re.search(s.rstrip("。.!? "))
        if m:
            # 마지막 3글자만 패턴 키로
            endings.append(m.group(1)[-3:])

    if not endings:
        return []

    counter = Counter(endings)
    most_common, count = counter.most_common(1)[0]
    ratio = count / len(endings)

    if ratio < 0.55 or count < 4:
        return []

    ev = [s for s in sentences if ending_re.search(s.rstrip("。.!? "))
          and (m := ending_re.search(s.rstrip("。.!? "))) and m.group(1)[-3:] == most_common][:4]
    return [_build_issue(
        issue_id="style_rhythm_monotone",
        issue_type="SENTENCE_RHYTHM",
        label_ko="단조로운 문장 리듬",
        description=f"문장의 {int(ratio*100)}%가 '{most_common}' 어미로 끝나 리듬이 단조롭습니다.",
        confidence=round(0.68 + ratio * 0.18, 3),
        reason="문장 종결 어미의 다양성이 부족하면 산문의 리듬감과 독자의 집중력이 저하됩니다.",
        evidence=ev,
        suggestion=(
            "일부 문장을 명사형 종결(예: '...는 침묵.')이나 현재형, 도치법으로 변환하여 "
            "리듬에 변화를 주세요."
        ),
    )]


def _check_show_dont_tell(sentences: list[str]) -> list[dict]:
    issues: list[dict] = []
    for i, s in enumerate(sentences):
        m = _TELL_VERBS.search(s)
        if m:
            issues.append(_build_issue(
                issue_id=f"style_tell_{i}",
                issue_type="SHOW_DONT_TELL",
                label_ko="감정 직접 서술",
                description=f"감정을 행동/감각 대신 직접 서술함: '{m.group(0)}'",
                confidence=0.72,
                reason=(
                    "감정을 직접 이름 붙이는 것보다 신체 반응, 행동, 환경을 통해 보여주는 것이 "
                    "더 강렬한 몰입감을 줍니다."
                ),
                evidence=[s],
                suggestion=(
                    f"'{m.group(0)}' 대신 신체 반응(심장이 빨라졌다, 손이 떨렸다)이나 "
                    "구체적인 행동으로 감정을 표현하세요."
                ),
                replace_hint=m.group(0),
                location=f"sentence_{i+1}",
            ))
    return issues


# ─── LLM 심층 분석 ────────────────────────────────────────────────────────────

_LLM_STYLE_SYSTEM = "당신은 한국어 소설 전문 문체 편집자입니다. 구조화된 JSON만 반환하세요."

_LLM_STYLE_PROMPT = """\
아래 한국어 장면을 문체 관점에서 분석하세요.

장면:
{scene}

기감지된 이슈 유형 (중복 금지): {existing_types}

다음 카테고리에서 새로운 문제를 찾아주세요:
- WORDINESS: 불필요한 단어/구문으로 인한 문장 비대화
- WEAK_DIALOGUE: 부자연스럽거나 설명적인 대화
- DESCRIPTION_DENSITY: 묘사 밀도 불균형 (과다 또는 부족)
- EXPOSITION: 자연스럽지 않은 정보 전달 (info-dump)
- SHOW_DONT_TELL: 직접 감정 서술 (기감지 없을 경우)

반드시 아래 JSON 형식으로만 응답:
{{
  "issues": [
    {{
      "issue_type": "카테고리",
      "description": "한국어로 간결하게",
      "confidence": 0.0~1.0,
      "reason": "왜 이것이 문제인지 (1~2문장)",
      "evidence": ["문제가 되는 실제 문장"],
      "suggestion": "구체적인 수정 방향",
      "replace_hint": "교체할 원문",
      "with_hint": "제안 대체문"
    }}
  ]
}}

이슈 없으면 {{"issues": []}}. JSON만 반환.\
"""


def _call_style_llm(
    text: str,
    existing_types: set[str],
    provider: "BaseLLMProvider",
) -> list[dict]:
    from backend.llm.providers.base import LLMMessage  # noqa: PLC0415

    prompt = _LLM_STYLE_PROMPT.format(
        scene=text.strip(),
        existing_types=", ".join(sorted(existing_types)) or "없음",
    )
    try:
        resp = provider.complete(
            [
                LLMMessage(role="system", content=_LLM_STYLE_SYSTEM),
                LLMMessage(role="user", content=prompt),
            ],
            max_tokens=900,
            temperature=0.15,
        )
        raw = resp.content.strip()
    except Exception:
        return []

    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end <= 0:
        return []
    try:
        data = json.loads(raw[start:end])
    except json.JSONDecodeError:
        return []

    issues: list[dict] = []
    for i, item in enumerate(data.get("issues", [])):
        itype = str(item.get("issue_type", "STYLE")).upper().strip()
        if itype in existing_types:
            continue
        desc = str(item.get("description", ""))
        issues.append(_build_issue(
            issue_id=f"style_llm_{i}_{itype.lower()}",
            issue_type=itype,
            label_ko=desc,
            description=desc,
            confidence=float(item.get("confidence", 0.70)),
            reason=str(item.get("reason", "")),
            evidence=list(item.get("evidence", [])),
            suggestion=str(item.get("suggestion", "")),
            replace_hint=str(item.get("replace_hint", "")),
            with_hint=str(item.get("with_hint", "")),
        ))
    return issues


# ─── 공개 API ─────────────────────────────────────────────────────────────────


class StyleAnalyzer:
    """
    두 단계 문체 분석기.

    1단계 (deterministic): 반복·페이싱·전환·리듬·감정 직서술 → 항상 실행
    2단계 (LLM):           더 깊은 분석 (wordiness, dialogue, density) → provider 필요
    """

    def analyze(
        self,
        text: str,
        provider: "BaseLLMProvider | None" = None,
        use_llm: bool = True,
    ) -> list[dict]:
        sentences = _split_sentences(text)
        if not sentences:
            return []

        issues: list[dict] = []

        # 1단계: 결정론적 검사
        issues.extend(_check_repetition(sentences, text))
        issues.extend(_check_repeated_action(sentences))
        issues.extend(_check_pacing(sentences))
        issues.extend(_check_weak_transition(sentences))
        issues.extend(_check_sentence_rhythm(sentences))
        issues.extend(_check_show_dont_tell(sentences))

        # 2단계: LLM 심층 분석 (선택)
        if use_llm and provider is not None:
            existing_types = {item["issue_type"] for item in issues}
            llm_issues = _call_style_llm(text, existing_types, provider)
            issues.extend(llm_issues)

        # 중복 제거 (같은 issue_type + 같은 첫 번째 evidence)
        seen: set[str] = set()
        deduped: list[dict] = []
        for item in issues:
            ev_key = item["evidence"][0] if item.get("evidence") else ""
            key = f"{item['issue_type']}|{ev_key[:60]}"
            if key not in seen:
                seen.add(key)
                deduped.append(item)

        return deduped
