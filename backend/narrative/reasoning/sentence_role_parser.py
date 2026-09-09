"""
한국어 문장 역할 파서 (Korean Sentence Role Parser)

행위 구조: Actor → Action → Target
  Actor    = 이/가/은/는 조사 → 행위 주체 → PBKD 검사 대상
  Target   = 을/를/에게/한테 조사 → 행위 대상 → 관계 검사 대상
  Action   = 동사 패턴         → 행위 유형 → 검사 종류 결정

한국어 이규칙 활용 처리:
  죽이다 → 죽였다 (죽이+었다, 이 탈락)
  속이다 → 속였다 (속이+었다, 이 탈락)
  → 원형과 활용형 모두 패턴에 등록
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ─── 데이터 모델 ─────────────────────────────────────────────────────────────


@dataclass
class SentenceRole:
    """문장 하나의 Actor/Action/Target 구조."""
    raw: str
    actor: str = ""      # 행위 주체 (이/가/은/는 조사로 식별) — PBKD 검사 대상
    action: str = ""     # 매칭된 동사 패턴
    target: str = ""     # 행위 대상 (을/를/에게/한테 조사로 식별) — 관계 검사 대상
    event_type: str = "" # BETRAYAL | MURDER | FEAR | LOVE | …
    check_kind: str = "" # "pbkd" | "relationship" | ""


# ─── 한국어 조사 패턴 ─────────────────────────────────────────────────────────

_NAME_PAT = r"[가-힣A-Za-z]{2,8}"

# 주격/화제 조사 — 조사를 필수로 요구 (optional 아님)
# 이: 이야기·이렇게 등과 구분하기 위해 뒤에 [가-힣], 공백, 또는 구두점이 와야 함
_ACTOR_RE = re.compile(
    rf"({_NAME_PAT})"
    r"(?:"
    r"이(?=[가-힣\s,.])|"   # 이 + (한글|공백|구두점)
    r"가(?=\s|[가-힣,.])|"  # 가
    r"은(?=\s|[가-힣,.])|"  # 은
    r"는(?=\s|[가-힣,.])"   # 는
    r")"
)

# 목적격/여격 조사 — 을/를(직접목적어) + 에게/한테(간접목적어·여격)
# 에게: 오린에게 충성했다, 오린에게 속였다
_TARGET_RE = re.compile(
    rf"({_NAME_PAT})"
    r"(?:"
    r"을(?=\s|[가-힣,.])|"
    r"를(?=\s|[가-힣,.])|"
    r"에게(?=\s|[가-힣,.])|"   # 여격: ~에게
    r"한테(?=\s|[가-힣,.])"    # 여격: ~한테
    r")"
)

# 일반 대명사 / 비고유명사 (캐릭터 이름 후보에서 제외)
_COMMON_NOUNS = {
    "그", "그녀", "그는", "그가", "그들", "그것",
    "나", "내가", "저", "제가", "너", "당신", "우리",
    "이", "저것", "이것", "것", "모든", "각각",
    "물", "바다", "강", "땅", "하늘", "숲", "산", "도시",
    "집", "방", "길", "문", "시간", "공간", "세계", "진실",
    "비밀", "충성", "신뢰", "사랑", "증오", "공포",
}


def _is_likely_name(word: str) -> bool:
    return len(word) >= 2 and word.lower() not in _COMMON_NOUNS


# ─── 사회적 행위 동사 패턴 ────────────────────────────────────────────────────
#
# 한국어 이규칙 처리:
#   죽이다 → 죽였다  (죽이+었 → 죽였, '이' 탈락 후 ㅕ 모음 합성)
#   속이다 → 속였다
#   해치다 → 해쳤다
#   보이다 → 보였다
#
# 해결: 원형 어근과 활용형(였 계열)을 모두 regex alternation으로 등록
#
# 형식: (regex_pattern, event_type, check_kind)
# check_kind:
#   "pbkd"         → Actor의 PBKD 검사 (행위가 성격·신념과 일치하는가)
#   "relationship" → Actor↔Target 관계 검사 (기존 관계와 일치하는가)

_SOCIAL_VERB_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # ── 배신 ──────────────────────────────────────────────────────────────────
    (re.compile(r"배신|배반"),                    "BETRAYAL",   "relationship"),
    # ── 살해 / 살인 ───────────────────────────────────────────────────────────
    # 죽이다 → 죽이|죽였  (죽이+었 → 죽였)
    (re.compile(r"죽이|죽였|살해|암살|처형"),      "MURDER",     "relationship"),
    # ── 공격 / 상해 ───────────────────────────────────────────────────────────
    # 해치다 → 해치|해쳤
    (re.compile(r"공격|해치|해쳤|상처"),           "ATTACK",     "relationship"),
    # ── 구조 / 보호 ───────────────────────────────────────────────────────────
    # 구하다→구했다, 지키다→지켰다 (하+었→했, 키+었→켰 축약)
    (re.compile(r"구하|구했|구출|도와|보호|지키|지켰"), "RESCUE",   "relationship"),
    # ── 용서 / 화해 ───────────────────────────────────────────────────────────
    (re.compile(r"용서|화해"),                    "FORGIVE",    "relationship"),
    # ── 기만 ──────────────────────────────────────────────────────────────────
    # 속이다 → 속이|속였
    (re.compile(r"속이|속였|거짓말"),              "DECEIVE",    "relationship"),
    # ── 충성 / 신뢰 ───────────────────────────────────────────────────────────
    (re.compile(r"충성|신뢰|믿"),                 "LOYAL",      "relationship"),
    # ── 감정 직접 서술 (PBKD 검사) ────────────────────────────────────────────
    (re.compile(r"사랑"),                        "LOVE",       "pbkd"),
    (re.compile(r"미워|증오"),                    "HATE",       "pbkd"),
    # 두려워하다 → 두려워|두려워했  /  무서워하다 → 무서워|무서워했
    (re.compile(r"두려워|무서워|두려움|무서움|공포"), "FEAR",      "pbkd"),
    (re.compile(r"희생"),                        "SACRIFICE",  "pbkd"),
    (re.compile(r"복수"),                        "REVENGE",    "pbkd"),
    (re.compile(r"포기"),                        "GIVE_UP",    "pbkd"),
]


# ─── 모순 관계 정의 ───────────────────────────────────────────────────────────

# {established_event_type: [contradicting_event_types]}
CONTRADICTION_MAP: dict[str, list[str]] = {
    "FEAR":    ["ATTACK", "MURDER"],                          # 두려워하던 것을 갑자기 공격
    "LOVE":    ["HATE", "MURDER", "BETRAYAL", "ATTACK"],      # 사랑하던 대상을 배신/살해/공격
    "LOYAL":   ["BETRAYAL", "MURDER", "ATTACK", "DECEIVE"],   # 충성하던 대상에게 반역
    "RESCUE":  ["HARM", "MURDER", "ATTACK"],                  # 구조한 대상을 해침
    "PROTECT": ["ATTACK", "MURDER", "BETRAYAL"],              # 보호하던 대상을 해침
}

# 관계를 확립하는(기억에 저장되는) 행위 유형
ESTABLISHES_RELATIONSHIP = {
    "FEAR", "LOVE", "LOYAL", "RESCUE", "PROTECT", "HELP",
}


# ─── 파서 ─────────────────────────────────────────────────────────────────────


def parse_sentence_role(sentence: str) -> SentenceRole:
    """
    한국어 문장 하나에서 Actor → Action → Target 구조를 파싱합니다.

    조사를 필수로 요구:
      이/가/은/는     → Actor  (행위 주체, PBKD 검사)
      을/를/에게/한테 → Target (행위 대상, 관계 검사)

    예시:
      "카엘이 오린을 배신했다."   → actor=카엘, action=배신,   target=오린
      "카엘이 오린을 죽였다."     → actor=카엘, action=죽였,   target=오린
      "오린이 카엘에게 충성했다." → actor=오린, action=충성,   target=카엘
      "오린이 카엘을 속였다."     → actor=오린, action=속이,   target=카엘
    """
    role = SentenceRole(raw=sentence)

    # Actor 추출 — 주격/화제 조사 이/가/은/는 필수
    for m in _ACTOR_RE.finditer(sentence):
        cand = m.group(1)
        if _is_likely_name(cand):
            role.actor = cand
            break

    # Target 추출 — 목적격/여격 조사 을/를/에게/한테 필수
    for m in _TARGET_RE.finditer(sentence):
        cand = m.group(1)
        if _is_likely_name(cand) and cand != role.actor:
            role.target = cand
            break

    # Action 분류 — regex 패턴 순차 적용
    for pattern, event_type, check_kind in _SOCIAL_VERB_PATTERNS:
        m = pattern.search(sentence)
        if m:
            role.action = m.group(0)
            role.event_type = event_type
            role.check_kind = check_kind
            break

    return role


def parse_all_roles(sentences: list[str]) -> list[SentenceRole]:
    return [parse_sentence_role(s) for s in sentences]


# ─── 관계 메모리 ──────────────────────────────────────────────────────────────


@dataclass
class CharacterRelationMemory:
    """텍스트에서 귀납한 캐릭터 관계/감정 상태."""
    # actor → {event_type → [targets]}
    relations: dict[str, dict[str, list[str]]] = field(
        default_factory=dict
    )

    def record(self, role: SentenceRole) -> None:
        if not role.actor or role.event_type not in ESTABLISHES_RELATIONSHIP:
            return
        rels = self.relations.setdefault(role.actor, {})
        key = role.event_type
        if key not in rels:
            rels[key] = []
        if role.target and role.target not in rels[key]:
            rels[key].append(role.target)

    def find_contradiction(
        self, role: SentenceRole
    ) -> tuple[str, str, list[str]] | None:
        """
        현재 행위(role)가 기존에 확립된 관계와 모순되는지 확인합니다.

        반환: (established_type, actor, conflicting_targets) 또는 None

        Target 처리 규칙:
          - Target이 명시되고 메모리에도 있으면 → 같은 대상끼리만 비교
          - 메모리에 Target이 없으면 (에게 미처리 등) → Actor 상태만으로 판별
          - 현재 role에 Target이 없으면 → Actor 상태 모순
        """
        if not role.actor or not role.event_type:
            return None

        # 현재 event_type을 모순으로 만드는 established type 목록
        contradicted_by = {
            et: victims
            for et, victims in CONTRADICTION_MAP.items()
            if role.event_type in victims
        }
        if not contradicted_by:
            return None

        actor_rels = self.relations.get(role.actor, {})
        for est_type, _ in contradicted_by.items():
            if est_type not in actor_rels:
                continue
            established_targets = actor_rels[est_type]

            if not established_targets:
                # 메모리에 Target 없음 → Actor 상태 자체가 모순
                return (est_type, role.actor, [])

            if role.target:
                # Target이 있으면 같은 대상 간 모순만 플래그
                if role.target in established_targets:
                    return (est_type, role.actor, [role.target])
            else:
                # 현재 문장에 Target 불명 → Actor 상태 모순
                return (est_type, role.actor, established_targets)

        return None


def build_character_memory(roles: list[SentenceRole]) -> CharacterRelationMemory:
    """문장 역할 목록에서 캐릭터 관계 메모리를 구축합니다."""
    memory = CharacterRelationMemory()
    for role in roles:
        memory.record(role)
    return memory
