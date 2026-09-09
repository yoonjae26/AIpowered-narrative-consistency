"""
Content Regulation Checker

Detects policy violations in narrative text:
  - 성적 콘텐츠 (Sexual content)
  - 폭력성·잔혹성 (Violence / graphic gore)
  - 혐오 표현·차별 (Hate speech / discrimination)
  - 기타 유해 콘텐츠 (Other harmful content)

Each violation carries:
  level   : "error" | "warning" | "info"
  category: display label
  code    : machine-readable key
  message : Korean description
  evidence: matched snippets (up to 3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RegulationViolation:
    level: str        # "error" | "warning" | "info"
    category: str     # 카테고리 한글 레이블
    code: str
    message: str
    evidence: list[str] = field(default_factory=list)


# ── Pattern Library ───────────────────────────────────────────────────────────

# 성적 콘텐츠 ─────────────────────────────────────────────────────────────────
_SEXUAL_ERROR: list[str] = [
    r"성관계", r"성행위", r"성교", r"섹스", r"자위", r"음란",
    r"포르노", r"야동", r"변태적",
    r"(음부|성기|생식기|유방|젖가슴).{0,10}(묘사|드러|노출|만지|빨)",
    r"(삽입|사정|오르가즘)",
    r"(성적).{0,6}(학대|폭행|추행|희롱)",
    r"(강간|성폭행|성추행)",
]

_SEXUAL_WARNING: list[str] = [
    r"관능적", r"육감적", r"욕정", r"색정",
    r"(알몸|나체|벗은 몸).{0,10}(묘사|노출|드러)",
    r"(가슴|몸매).{0,8}(탐하|훑어|빤히)",
    r"(침대|잠자리).{0,8}(함께|같이).{0,8}(하룻밤|하룻밤)",
    r"음탕", r"淫",
]

# 폭력성·잔혹성 ───────────────────────────────────────────────────────────────
_VIOLENCE_ERROR: list[str] = [
    r"신체를.{0,10}절단",
    r"(머리|팔|다리|손|발).{0,6}(잘리|절단|끊어|뜯어)",
    r"내장.{0,10}(흘러|쏟아|드러)",
    r"(고문|능지처참|거열형)",
    r"(살점|뼈|두개골).{0,8}(으스러|부서|박살)",
    r"(고통|비명).{0,8}즐기",
    r"(잔혹|잔인).{0,8}(묘사|장면|방식).{0,8}(반복|상세|구체)",
    r"(아동|어린이|미성년자).{0,10}(폭행|학대|살해|살인)",
]

_VIOLENCE_WARNING: list[str] = [
    r"(피가|선혈이|핏물이).{0,10}(흘러|낭자|낭자하)",
    r"(잔혹|잔인|끔찍).{0,6}(하게|히|하다|한)",
    r"(고통스러|괴로워).{0,6}하는.{0,10}장면",
    r"(죽이|살해).{0,6}(즐기|쾌감)",
    r"(자살|자해).{0,8}(방법|시도|장면).{0,6}(상세|구체)",
]

# 혐오 표현·차별 ──────────────────────────────────────────────────────────────
_HATE_ERROR: list[str] = [
    r"(여성|남성|장애인|노인|외국인|흑인|유대인|무슬림).{0,10}(열등|하등|쓸모없|쓰레기|벌레)",
    r"(민족|인종|성별|장애).{0,6}(비하|혐오|차별).{0,6}(표현|묘사)",
    r"(특정 집단).{0,10}(말살|청소|제거)",
    r"(여자|남자|동성애자|트랜스젠더).{0,8}(혐오|역겹|구역질)",
]

_HATE_WARNING: list[str] = [
    r"(여성|남성|노인|외국인).{0,8}(이기|라서|때문에).{0,8}(열등|못하|떨어)",
    r"(인종|민족|국적).{0,6}(이유로|때문에).{0,8}(배제|차별)",
    r"(비정상|변태|정신병).{0,8}(동성|동성애|성소수)",
]

# 기타 유해 콘텐츠 ────────────────────────────────────────────────────────────
_OTHER_WARNING: list[str] = [
    r"(마약|마약류|헤로인|코카인|필로폰|히로뽕).{0,8}(제조|합성|구입|판매)",
    r"(도박|불법 도박|불법 베팅).{0,8}(방법|사이트|안내)",
    r"(폭탄|폭발물|총기).{0,8}(제조|밀수|구입|설계).{0,6}(방법|안내)",
    r"(사기|해킹|피싱).{0,8}(방법|기술|코드).{0,6}(안내|공유|교육)",
]


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]


_COMPILED: dict[str, tuple[str, str, str, list[re.Pattern[str]]]] = {
    # key: (level, category, code, patterns)
    "sexual_error":    ("error",   "성적 콘텐츠",   "sexual_content_explicit",   _compile(_SEXUAL_ERROR)),
    "sexual_warning":  ("warning", "성적 콘텐츠",   "sexual_content_suggestive", _compile(_SEXUAL_WARNING)),
    "violence_error":  ("error",   "폭력·잔혹성",   "graphic_violence",          _compile(_VIOLENCE_ERROR)),
    "violence_warning":("warning", "폭력·잔혹성",   "violence_mature",           _compile(_VIOLENCE_WARNING)),
    "hate_error":      ("error",   "혐오·차별",     "hate_speech",               _compile(_HATE_ERROR)),
    "hate_warning":    ("warning", "혐오·차별",     "discriminatory_content",    _compile(_HATE_WARNING)),
    "other_warning":   ("warning", "기타 유해",     "harmful_content",           _compile(_OTHER_WARNING)),
}

_MESSAGES: dict[str, str] = {
    "sexual_content_explicit":   "명시적 성적 묘사가 포함된 구절이 감지됐습니다. 플랫폼 규정 위반 가능성이 높습니다.",
    "sexual_content_suggestive": "성적으로 암시적인 표현이 포함돼 있습니다. 독자층에 따라 규정 위반이 될 수 있습니다.",
    "graphic_violence":          "신체 훼손 또는 잔혹한 폭력 묘사가 감지됐습니다. 규정 위반 가능성이 높습니다.",
    "violence_mature":           "성인 대상 폭력·잔혹성 표현이 포함돼 있습니다. 연령 등급 표시가 필요할 수 있습니다.",
    "hate_speech":               "특정 집단에 대한 혐오 표현이 감지됐습니다. 플랫폼 규정 위반입니다.",
    "discriminatory_content":    "차별적 표현이 포함돼 있습니다. 편집 검토가 필요합니다.",
    "harmful_content":           "불법 행위 또는 유해 콘텐츠 관련 표현이 감지됐습니다.",
}


def _extract_evidence(text: str, pattern: re.Pattern[str], max_items: int = 3) -> list[str]:
    snippets: list[str] = []
    for m in pattern.finditer(text):
        start = max(0, m.start() - 10)
        end = min(len(text), m.end() + 10)
        snippet = ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")
        snippets.append(snippet)
        if len(snippets) >= max_items:
            break
    return snippets


class ContentRegulationChecker:
    """Rule-based Korean content regulation checker."""

    def check(self, text: str) -> list[RegulationViolation]:
        violations: list[RegulationViolation] = []

        for key, (level, category, code, patterns) in _COMPILED.items():
            all_evidence: list[str] = []
            for pattern in patterns:
                all_evidence.extend(_extract_evidence(text, pattern))
                if len(all_evidence) >= 3:
                    break

            if all_evidence:
                violations.append(RegulationViolation(
                    level=level,
                    category=category,
                    code=code,
                    message=_MESSAGES[code],
                    evidence=all_evidence[:3],
                ))

        # Sort: error first, then warning, then info
        _order = {"error": 0, "warning": 1, "info": 2}
        violations.sort(key=lambda v: _order.get(v.level, 9))
        return violations
