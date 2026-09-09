#!/usr/bin/env python3
"""
홍길동전 Canonical Dataset Generator
75 scenes → 60 chapters (15 merges)

Each chapter includes:
  - prose text (summary + expanded beats → 95% original story)
  - ground_truth labels for Precision / Recall measurement
  - adversarial_test: one intentional corruption → tests FP detection
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data" / "honggildongjeon_scenes.json"
OUTPUT = ROOT / "data" / "honggildongjeon_canonical.json"

# ──────────────────────────────────────────────
# Chapter mapping: chapter_no → list of scene seq numbers
# 75 scenes → 60 chapters (exactly 15 two-scene merges)
# ──────────────────────────────────────────────
CHAPTER_MAP: dict[int, list[int]] = {
    1:  [1, 2],   # 홍승상 가문 + 청룡몽
    2:  [3],
    3:  [4],
    4:  [5],
    5:  [6],
    6:  [7, 8],   # 칠월망일 + 부친충돌
    7:  [9],
    8:  [10, 11], # 곡산모 + 관상녀포섭
    9:  [12],
    10: [13],
    11: [14, 15], # 승상병환 + 살해모의
    12: [16],
    13: [17],
    14: [18],
    15: [19],
    16: [20],
    17: [21, 22], # 변괴발각 + 방랑
    18: [23],
    19: [24],
    20: [25],
    21: [26, 27], # 해인사정탐 + 승려유인
    22: [28],
    23: [29],
    24: [30],
    25: [31, 32], # 함경감영습격 + 탈취
    26: [33],
    27: [34],
    28: [35],
    29: [36, 37], # 임금진노 + 이업
    30: [38],
    31: [39],
    32: [40, 41], # 홍가투옥 + 방서
    33: [42],
    34: [43],
    35: [44, 45], # 승상기절 + 자기변호
    36: [46],
    37: [47],
    38: [48],
    39: [49],
    40: [50],
    41: [51],
    42: [52],
    43: [53, 54], # 을동조우 + 격퇴
    44: [55],
    45: [56],
    46: [57],
    47: [58],
    48: [59],
    49: [60],
    50: [61],
    51: [62],
    52: [63],
    53: [64],
    54: [65, 66], # 율도국출병 + 격서
    55: [67, 68], # 전투 + 율도왕자결
    56: [69, 70], # 등극 + 태평성대
    57: [71, 72], # 모친승하 + 왕위이양
    58: [73],
    59: [74],
    60: [75],
}

# ──────────────────────────────────────────────
# Per-chapter ground truth labels
# ──────────────────────────────────────────────
# Format: chapter_no → {
#   "required_event_types": [types that MUST appear],
#   "forbidden_event_types": [types that should NOT appear],
#   "event_count_range": [min, max],
#   "expected_relationships": [{"from","to","type"}],
#   "pbkd_updates": [character names whose state changes],
#   "expected_contradictions": int (usually 0),
#   "notes": str,
# }
GROUND_TRUTH: dict[int, dict[str, Any]] = {
    1: {
        "required_event_types": ["char_trait", "world_state_change", "scene_opens"],
        "event_count_range": [3, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍 승상"],
        "expected_contradictions": 0,
        "notes": "도입부: 홍 승상 인물 소개, 태평성대 배경 설정",
    },
    2: {
        "required_event_types": ["char_trait", "scene_opens"],
        "event_count_range": [3, 12],
        "expected_relationships": [{"from": "홍 승상", "to": "유씨 부인", "type": "spouse"}],
        "pbkd_updates": ["홍 승상", "유씨 부인"],
        "expected_contradictions": 0,
        "notes": "유씨 부인 첫 등장. 부인 거절 → 춘섬과 동침. 춘섬 관계 형성.",
    },
    3: {
        "required_event_types": ["char_trait", "timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [{"from": "홍 승상", "to": "홍길동", "type": "parent"}],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "홍길동 탄생 (오색운무). 천비 소생이라는 핵심 설정.",
    },
    4: {
        "required_event_types": ["char_trait", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "길동 8세. 총명, 기골비상. 차별 인지 시작.",
    },
    5: {
        "required_event_types": ["char_trait"],
        "event_count_range": [2, 10],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "천비 소생 신분 차별 인식. 부형을 부형이라 못 부르는 한.",
    },
    6: {
        "required_event_types": ["char_trait", "dialogue"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "홍 승상"],
        "expected_contradictions": 0,
        "notes": "칠월 망일 독백 (왕후장상 씨 없다). 부친과 갈등 직접 충돌.",
    },
    7: {
        "required_event_types": ["dialogue", "char_trait"],
        "event_count_range": [3, 12],
        "expected_relationships": [{"from": "홍길동", "to": "춘섬", "type": "parent_child"}],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "어머니 춘섬과의 대화. 조선 떠날 뜻 내비침.",
    },
    8: {
        "required_event_types": ["char_trait"],
        "event_count_range": [3, 12],
        "expected_relationships": [{"from": "초낭", "to": "관상녀", "type": "conspiracy"}],
        "pbkd_updates": ["초낭"],
        "expected_contradictions": 0,
        "notes": "초낭의 시기심 소개. 관상녀 포섭 모의. 핵심 악역 설정.",
    },
    9: {
        "required_event_types": ["char_trait", "scene_opens"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍 승상", "관상녀"],
        "expected_contradictions": 0,
        "notes": "관상녀 내당 방문. 대감 상 읽기. 신뢰 획득.",
    },
    10: {
        "required_event_types": ["dialogue", "timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍 승상", "홍길동"],
        "expected_contradictions": 0,
        "notes": "왕후장상 예언. 승상 대경실색. 길동에 대한 두려움 시작.",
    },
    11: {
        "required_event_types": ["char_trait", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [{"from": "초낭", "to": "특자", "type": "hired"}],
        "pbkd_updates": ["초낭", "홍 승상"],
        "expected_contradictions": 0,
        "notes": "승상 침식 불안. 초낭→특자 자객 고용. 홍길현도 동조.",
    },
    12: {
        "required_event_types": ["timeline_beat"],
        "event_count_range": [2, 8],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "까마귀 경고 → 길동 팔진법 설치. 도술 첫 등장.",
    },
    13: {
        "required_event_types": ["timeline_beat", "dialogue"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "특자"],
        "expected_contradictions": 0,
        "notes": "특자 격퇴. 길동 도술 발휘. 자객 처치.",
    },
    14: {
        "required_event_types": ["timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "관상녀"],
        "expected_contradictions": 0,
        "notes": "관상녀 처단. 길동 분노 표출.",
    },
    15: {
        "required_event_types": ["dialogue", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "홍 승상"],
        "expected_contradictions": 0,
        "notes": "부친께 하직 고함. 승상 '부친'으로 불러도 된다는 허락.",
    },
    16: {
        "required_event_types": ["dialogue", "char_trait"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "춘섬"],
        "expected_contradictions": 0,
        "notes": "어머니 춘섬과 이별. 길동 집을 떠남.",
    },
    17: {
        "required_event_types": ["timeline_beat", "char_trait"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["초낭", "홍 승상"],
        "expected_contradictions": 0,
        "notes": "변괴 발각 (특자/관상녀 시신). 초낭 고변. 길동 집 떠남 완료.",
    },
    18: {
        "required_event_types": ["travel", "timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "길동 방랑. 도적 소굴 발견. 활빈당 arc 시작.",
    },
    19: {
        "required_event_types": ["timeline_beat", "dialogue"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "초부석 들기 시험. 천여 근 바위 거뜬히 들어 장수 인정받음.",
    },
    20: {
        "required_event_types": ["timeline_beat", "char_trait"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "맹세 (백마 피). 도적 장수 취임. 활빈당 조직 완성.",
    },
    21: {
        "required_event_types": ["travel", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "해인사 정탐 + 승려 유인. 재상 자제 위장 잠입.",
    },
    22: {
        "required_event_types": ["timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "해인사 재물 탈취. 수천 승려 결박. 수만금 약탈.",
    },
    23: {
        "required_event_types": ["timeline_beat", "travel"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "관군 추격 유인. 노승 위장으로 관군 방향 오도.",
    },
    24: {
        "required_event_types": ["timeline_beat", "dialogue"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "활빈당 선언. '백성 재물 추호도 탈취 않겠다'. 정의적 도적 정체성.",
    },
    25: {
        "required_event_types": ["timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "함경감영 능소 화재 위장 → 창고 탈취. 도술로 군기 절취.",
    },
    26: {
        "required_event_types": ["timeline_beat", "world_state_change"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "북문 방 붙임. '활빈당 당수 홍길동' 공개 선언. 책임 표명.",
    },
    27: {
        "required_event_types": ["timeline_beat", "world_state_change"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "분신술. 초인 일곱 만들어 팔도 동시 파견.",
    },
    28: {
        "required_event_types": ["world_state_change", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "팔도 동일자 동시 작란. 임금 대경실색. 국가적 위기.",
    },
    29: {
        "required_event_types": ["char_trait", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["이업"],
        "expected_contradictions": 0,
        "notes": "임금 진노. 포도대장 이업 등장. 홍가 투옥 계획.",
    },
    30: {
        "required_event_types": ["timeline_beat", "dialogue"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "이업"],
        "expected_contradictions": 0,
        "notes": "이업 주점에서 길동과 조우. 서생 위장한 길동에 속음.",
    },
    31: {
        "required_event_types": ["timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["이업"],
        "expected_contradictions": 0,
        "notes": "이업 가죽부대에 갇힘. 길동 조종술. 이업 수치 후 방면.",
    },
    32: {
        "required_event_types": ["timeline_beat", "world_state_change"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍 승상", "홍길현"],
        "expected_contradictions": 0,
        "notes": "홍 승상 금부 투옥. 홍길현 경상감사 임명. 방서 발송.",
    },
    33: {
        "required_event_types": ["dialogue", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "홍길현"],
        "expected_contradictions": 0,
        "notes": "형 길현과 재회. 형의 설득. 길동 자수 결심.",
    },
    34: {
        "required_event_types": ["timeline_beat", "world_state_change"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "여덟 길동 동시 압송. 각 도에서 참 길동이라 주장.",
    },
    35: {
        "required_event_types": ["dialogue", "timeline_beat"],
        "event_count_range": [5, 20],
        "expected_relationships": [],
        "pbkd_updates": ["홍 승상", "홍길동"],
        "expected_contradictions": 0,
        "notes": "임금 친국. 승상 기절. 길동 자기변호 (활빈당 의리). 도술 탈출.",
    },
    36: {
        "required_event_types": ["dialogue", "timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "병조판서 유지 요구. 사문에 방 붙임.",
    },
    37: {
        "required_event_types": ["timeline_beat", "world_state_change"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "동대문 밖 진세. 신장 호령. 조정 간신 처벌.",
    },
    38: {
        "required_event_types": ["timeline_beat", "world_state_change"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "병조판서 직첩 수여. 임금 길동 재주 인정.",
    },
    39: {
        "required_event_types": ["dialogue", "travel"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "임금 하직. 구름 타고 떠남. 이후 작란 없음.",
    },
    40: {
        "required_event_types": ["travel", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "정조 삼천 석 받아 조선 출발. 서강에서 떠남.",
    },
    41: {
        "required_event_types": ["world_state_change", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "제도 정착. 궁실, 창고 건설. 3년 만에 군기 군량 충실.",
    },
    42: {
        "required_event_types": ["travel", "timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [{"from": "홍길동", "to": "백용", "type": "encountered"}],
        "pbkd_updates": ["홍길동", "백용"],
        "expected_contradictions": 0,
        "notes": "망당산 약초. 백용 딸 실종 정보 접수.",
    },
    43: {
        "required_event_types": ["timeline_beat", "travel"],
        "event_count_range": [5, 20],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "을동"],
        "expected_contradictions": 0,
        "notes": "을동 요귀 조우. 화살로 처치 시도. 을동 소굴 추적 → 격퇴.",
    },
    44: {
        "required_event_types": ["timeline_beat", "relationship_forms"],
        "event_count_range": [4, 15],
        "expected_relationships": [
            {"from": "홍길동", "to": "백소저", "type": "married"},
            {"from": "홍길동", "to": "정씨 부인", "type": "married"},
            {"from": "홍길동", "to": "통씨 부인", "type": "married"},
        ],
        "pbkd_updates": ["홍길동", "백소저"],
        "expected_contradictions": 0,
        "notes": "세 부인 구출 후 혼인. 백소저 정실. 정씨/통씨 시첩.",
    },
    45: {
        "required_event_types": ["world_state_change", "timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "제도 귀환. 번영. 백용 부원군 지위.",
    },
    46: {
        "required_event_types": ["timeline_beat", "char_trait"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "천문으로 부친 임종 예감. 통곡. 불효자 자탄.",
    },
    47: {
        "required_event_types": ["timeline_beat", "travel"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "일봉산에 부친 묘터 마련. 귀국 선박 준비.",
    },
    48: {
        "required_event_types": ["travel", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "유씨 부인", "춘섬"],
        "expected_contradictions": 0,
        "notes": "조선 귀환. 승상댁 방문. 모친 춘섬 상면.",
    },
    49: {
        "required_event_types": ["timeline_beat", "dialogue"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍 승상"],
        "expected_contradictions": 0,
        "notes": "승상 임종. 유언 (길동 모친 후대). 구십 세 별세.",
    },
    50: {
        "required_event_types": ["timeline_beat", "dialogue"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "홍길현"],
        "expected_contradictions": 0,
        "notes": "부친 장례. 형 길현 묏자리 문제 논의. 일봉산 소개.",
    },
    51: {
        "required_event_types": ["travel", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "홍길현"],
        "expected_contradictions": 0,
        "notes": "부친 안장 (현지 능묘 수준). 모친 춘섬 제도로 데려감.",
    },
    52: {
        "required_event_types": ["travel", "dialogue"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "홍길현"],
        "expected_contradictions": 0,
        "notes": "형 홍길현과 이별. 남북 천리 이별의 정.",
    },
    53: {
        "required_event_types": ["world_state_change", "timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "율도국 정복 결의. 제도에서 출병 준비.",
    },
    54: {
        "required_event_types": ["world_state_change", "travel"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "맹춘", "김인수"],
        "expected_contradictions": 0,
        "notes": "출병 (기병5000, 보졸2만). 칠십여 성 함락. 율도왕께 격서.",
    },
    55: {
        "required_event_types": ["timeline_beat", "world_state_change"],
        "event_count_range": [5, 20],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "율도왕"],
        "expected_contradictions": 0,
        "notes": "맹춘 양관 전투. 율도왕 함정에 빠짐. 율도왕 자결.",
    },
    56: {
        "required_event_types": ["world_state_change", "timeline_beat"],
        "event_count_range": [4, 15],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동"],
        "expected_contradictions": 0,
        "notes": "등극. 백소저 왕비. 봉직. 시화연풍 태평성대.",
    },
    57: {
        "required_event_types": ["timeline_beat", "char_trait"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "춘섬"],
        "expected_contradictions": 0,
        "notes": "태평 수십 년. 모친 춘섬 73세 승하. 왕위 태자에게 이양.",
    },
    58: {
        "required_event_types": ["travel", "timeline_beat"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "백소저"],
        "expected_contradictions": 0,
        "notes": "월영산 선도 수행. 곡식 끊고 천지정기 수련.",
    },
    59: {
        "required_event_types": ["timeline_beat", "world_state_change"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길동", "백소저"],
        "expected_contradictions": 0,
        "notes": "뇌성벽력 후 오색운무. 대왕 모비 백일승천.",
    },
    60: {
        "required_event_types": ["timeline_beat", "char_trait"],
        "event_count_range": [3, 12],
        "expected_relationships": [],
        "pbkd_updates": ["홍길현", "유씨 부인"],
        "expected_contradictions": 0,
        "notes": "에필로그. 길현 조선 조정 승상. 대부인 길현이 안장. 홍길동전 결말.",
    },
}

# ──────────────────────────────────────────────
# Adversarial test cases  (one per chapter, injected corruption)
# Each adversarial test changes ONE factual detail that should trigger
# a PBKD / consistency contradiction in the pipeline.
# ──────────────────────────────────────────────
ADVERSARIAL: dict[int, dict[str, str]] = {
    1:  {"field": "summary", "corruption": "timeline", "detail": "세조대왕 즉위 15년", "original": "세종대왕 즉위 15년", "expected_flag": "timeline_agent"},
    2:  {"field": "beat", "corruption": "character_behavior", "detail": "유씨 부인이 기꺼이 응하여 동침하였다", "original": "유씨 부인이 거절하였다", "expected_flag": "consistency_agent"},
    3:  {"field": "beat", "corruption": "character_trait", "detail": "홍길동은 정실 부인 유씨 복중에서 태어났다", "original": "홍길동은 천비 춘섬 소생이다", "expected_flag": "character_agent"},
    4:  {"field": "beat", "corruption": "timeline", "detail": "길동의 나이 이십 세에", "original": "길동의 나이 팔 세에", "expected_flag": "timeline_agent"},
    5:  {"field": "beat", "corruption": "character_trait", "detail": "길동은 아비를 아비라, 형을 형이라 부를 수 있었다", "original": "길동은 아비를 아비라 못 하고 형을 형이라 부르지 못했다", "expected_flag": "character_agent"},
    6:  {"field": "beat", "corruption": "character_behavior", "detail": "홍 승상이 길동의 불평을 들어 기꺼이 허락하였다", "original": "홍 승상이 길동을 꾸짖었다", "expected_flag": "consistency_agent"},
    7:  {"field": "beat", "corruption": "relationship", "detail": "길동이 어머니 유씨 부인에게 하소연하였다", "original": "길동이 어머니 춘섬에게 하소연하였다", "expected_flag": "character_agent"},
    8:  {"field": "summary", "corruption": "character_trait", "detail": "초낭은 길동을 아끼는 마음에서 관상녀를 불렀다", "original": "초낭은 길동을 시기하여 관상녀를 포섭하였다", "expected_flag": "character_agent"},
    9:  {"field": "beat", "corruption": "timeline", "detail": "관상녀는 서대문 밖에 사는 인물이었다", "original": "관상녀는 동대문 밖에 사는 인물이었다", "expected_flag": "lore_agent"},
    10: {"field": "beat", "corruption": "character_trait", "detail": "관상녀가 길동의 상은 평범하다고 말하였다", "original": "관상녀가 길동의 상은 성즉 군왕지상이라 예언하였다", "expected_flag": "character_agent"},
    11: {"field": "beat", "corruption": "character_behavior", "detail": "홍 승상이 길동을 죽이라 직접 명하였다", "original": "홍 승상이 차마 길동을 죽이지 못하였다", "expected_flag": "character_agent"},
    12: {"field": "beat", "corruption": "character_trait", "detail": "길동이 까마귀 소리를 무시하고 잠들었다", "original": "길동이 까마귀 경고를 듣고 팔진을 쳤다", "expected_flag": "character_agent"},
    13: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 특자에게 패하여 달아났다", "original": "길동이 도술로 특자를 격퇴하였다", "expected_flag": "character_agent"},
    14: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 관상녀를 불쌍히 여겨 살려 보냈다", "original": "길동이 관상녀의 목을 베었다", "expected_flag": "character_agent"},
    15: {"field": "beat", "corruption": "relationship", "detail": "홍 승상이 끝까지 아비라 부르는 것을 허락하지 않았다", "original": "홍 승상이 그날부터 부친이라 불러도 된다고 허락하였다", "expected_flag": "character_agent"},
    16: {"field": "beat", "corruption": "character_behavior", "detail": "춘섬이 길동을 강제로 붙들어 떠나지 못하게 하였다", "original": "춘섬이 눈물을 흘리며 길동을 보냈다", "expected_flag": "character_agent"},
    17: {"field": "beat", "corruption": "character_behavior", "detail": "초낭은 변괴 발각 후 아무 처벌도 받지 않았다", "original": "초낭은 승상에게 크게 꾸중을 들었다", "expected_flag": "consistency_agent"},
    18: {"field": "beat", "corruption": "character_trait", "detail": "길동은 도적 소굴에서 장수 자리를 거절하였다", "original": "길동은 스스로 도적 장수가 되겠다고 자청하였다", "expected_flag": "character_agent"},
    19: {"field": "beat", "corruption": "timeline", "detail": "초부석 무게는 오십 근이었다", "original": "초부석 무게는 천여 근이었다", "expected_flag": "lore_agent"},
    20: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 맹세 없이 장수 취임을 선포하였다", "original": "길동이 백마 피를 마시며 군사들과 맹세하였다", "expected_flag": "character_agent"},
    21: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 해인사를 처음부터 폭력으로 습격하였다", "original": "길동이 재상 자제로 위장하여 해인사에 잠입하였다", "expected_flag": "character_agent"},
    22: {"field": "beat", "corruption": "world_state", "detail": "해인사 승려들이 길동에게 대적하여 싸웠다", "original": "해인사 승려들은 결박당하여 저항하지 못하였다", "expected_flag": "consistency_agent"},
    23: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 관군에게 붙잡혀 감옥에 갔다", "original": "길동이 노승으로 위장하여 관군을 북편 소로로 유인하였다", "expected_flag": "character_agent"},
    24: {"field": "beat", "corruption": "character_trait", "detail": "길동은 불쌍한 백성의 재물도 취하였다", "original": "길동은 백성의 재물은 추호도 탈취하지 않겠다고 선언하였다", "expected_flag": "character_agent"},
    25: {"field": "beat", "corruption": "world_state", "detail": "함경감영 습격에서 길동이 직접 불을 능소에 질렀다", "original": "길동은 능소에는 불이 닿지 않게 하였다", "expected_flag": "character_agent"},
    26: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 익명으로 방을 붙였다", "original": "길동이 '활빈당 당수 홍길동'이라는 이름으로 방을 붙였다", "expected_flag": "character_agent"},
    27: {"field": "beat", "corruption": "timeline", "detail": "길동이 초인 세 명을 만들었다", "original": "길동이 초인 일곱을 만들었다", "expected_flag": "lore_agent"},
    28: {"field": "beat", "corruption": "world_state", "detail": "각 도의 작란 날짜가 모두 달랐다", "original": "각 도의 작란 날짜가 동월 동일이었다", "expected_flag": "timeline_agent"},
    29: {"field": "beat", "corruption": "character_trait", "detail": "이업은 겁이 많아 자원하지 않았다", "original": "이업이 스스로 나서서 길동 토벌을 자원하였다", "expected_flag": "character_agent"},
    30: {"field": "beat", "corruption": "character_behavior", "detail": "이업이 길동의 정체를 처음부터 알아보았다", "original": "이업은 서생으로 위장한 길동에게 속아 산중에 따라갔다", "expected_flag": "character_agent"},
    31: {"field": "beat", "corruption": "character_behavior", "detail": "이업이 길동을 포박하여 한양으로 압송하였다", "original": "길동이 이업을 가죽부대에 넣어 수치를 주고 방면하였다", "expected_flag": "character_agent"},
    32: {"field": "beat", "corruption": "relationship", "detail": "홍길현이 길동을 잡는 것을 거부하였다", "original": "홍길현이 임금 명으로 경상감사에 임명되어 길동을 잡으라는 방서를 내렸다", "expected_flag": "character_agent"},
    33: {"field": "beat", "corruption": "character_behavior", "detail": "홍길현이 길동을 즉시 포박하여 압송하였다", "original": "홍길현이 길동과 하룻밤 정담을 나누고 다음 날 압송하였다", "expected_flag": "character_agent"},
    34: {"field": "beat", "corruption": "timeline", "detail": "각 도에서 길동 두 명이 압송되었다", "original": "각 도에서 길동 여덟 명이 동시에 압송되었다", "expected_flag": "lore_agent"},
    35: {"field": "beat", "corruption": "character_behavior", "detail": "홍 승상이 여덟 길동 중 참 길동을 바로 알아보았다", "original": "홍 승상은 참 길동을 가리지 못하고 기절하였다", "expected_flag": "character_agent"},
    36: {"field": "beat", "corruption": "character_trait", "detail": "길동이 임금에게 영의정 자리를 요구하였다", "original": "길동이 병조판서 유지만 주면 잡히겠다고 하였다", "expected_flag": "character_agent"},
    37: {"field": "beat", "corruption": "world_state", "detail": "진세에서 길동이 관군에게 패하였다", "original": "진세에서 길동이 조정 간신들을 잡아 곤장 쳤다", "expected_flag": "consistency_agent"},
    38: {"field": "beat", "corruption": "world_state", "detail": "임금이 길동을 끝까지 거부하였다", "original": "임금이 병조판서 직첩을 주어 길동을 달랬다", "expected_flag": "consistency_agent"},
    39: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 임금을 만나지 않고 몰래 조선을 떠났다", "original": "길동이 임금을 야간에 직접 만나 구름을 타고 하직하였다", "expected_flag": "character_agent"},
    40: {"field": "beat", "corruption": "timeline", "detail": "길동이 정조 삼백 석을 받았다", "original": "길동이 정조 삼천 석을 받았다", "expected_flag": "lore_agent"},
    41: {"field": "beat", "corruption": "world_state", "detail": "제도에서 길동이 농업을 금하였다", "original": "제도에서 길동이 군사에게 농업을 힘쓰게 하였다", "expected_flag": "character_agent"},
    42: {"field": "beat", "corruption": "world_state", "detail": "백용의 딸이 스스로 집을 나갔다", "original": "백용의 딸이 풍우 속에 요귀에게 납치되었다", "expected_flag": "consistency_agent"},
    43: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 을동과 협상하여 여인들을 평화롭게 데려왔다", "original": "길동이 을동을 도술로 격퇴하고 여인들을 구출하였다", "expected_flag": "character_agent"},
    44: {"field": "beat", "corruption": "relationship", "detail": "길동이 백소저 한 명과만 혼인하였다", "original": "길동이 백소저와 정씨·통씨 세 부인과 혼인하였다", "expected_flag": "lore_agent"},
    45: {"field": "beat", "corruption": "world_state", "detail": "제도가 전쟁으로 황폐해졌다", "original": "제도가 번영하여 백성이 편안하였다", "expected_flag": "consistency_agent"},
    46: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 천문을 보지 않고 부친 임종 소식을 무시하였다", "original": "길동이 천문으로 부친 임종을 예감하고 통곡하였다", "expected_flag": "character_agent"},
    47: {"field": "beat", "corruption": "world_state", "detail": "길동이 부친 묏자리를 조선에 미리 마련하였다", "original": "길동이 제도 일봉산에 부친 묏자리를 미리 마련하였다", "expected_flag": "lore_agent"},
    48: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 귀국하여 형 길현을 만나지 않았다", "original": "길동이 귀국하여 형 길현 및 모친 춘섬과 상면하였다", "expected_flag": "character_agent"},
    49: {"field": "beat", "corruption": "timeline", "detail": "홍 승상이 오십 세에 별세하였다", "original": "홍 승상이 구십 세에 별세하였다", "expected_flag": "timeline_agent"},
    50: {"field": "beat", "corruption": "character_behavior", "detail": "길현이 묏자리를 찬성하고 바로 일봉산에 안장하였다", "original": "길현이 처음에는 불합하다 했으나 오색 기운을 보고 수긍하였다", "expected_flag": "character_agent"},
    51: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 부친 안장 후 혼자 제도로 돌아갔다", "original": "길동이 모친 춘섬을 제도로 함께 데려갔다", "expected_flag": "character_agent"},
    52: {"field": "beat", "corruption": "relationship", "detail": "형 길현이 길동과 함께 율도국으로 떠났다", "original": "형 길현이 조선으로 돌아가고 두 형제는 이별하였다", "expected_flag": "character_agent"},
    53: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 율도국과 평화협상을 시도하였다", "original": "길동이 제군과 의논하여 율도국 정복을 결의하였다", "expected_flag": "character_agent"},
    54: {"field": "beat", "corruption": "timeline", "detail": "율도국 원정군은 기병 오백, 보졸 이천이었다", "original": "율도국 원정군은 기병 오천, 보졸 이만이었다", "expected_flag": "lore_agent"},
    55: {"field": "beat", "corruption": "character_behavior", "detail": "율도왕이 항복하여 신하가 되었다", "original": "율도왕이 포위 속에 자결하였다", "expected_flag": "character_agent"},
    56: {"field": "beat", "corruption": "relationship", "detail": "길동이 등극 후 정씨 부인을 왕비로 봉하였다", "original": "길동이 등극 후 백소저를 중전왕비로 봉하였다", "expected_flag": "character_agent"},
    57: {"field": "beat", "corruption": "timeline", "detail": "모친 춘섬이 오십 세에 승하하였다", "original": "모친 춘섬이 73세에 승하하였다", "expected_flag": "timeline_agent"},
    58: {"field": "beat", "corruption": "world_state", "detail": "길동이 왕위를 유지하면서 수련하였다", "original": "길동이 왕위를 태자에게 이양한 후 월영산에서 선도를 수련하였다", "expected_flag": "consistency_agent"},
    59: {"field": "beat", "corruption": "character_behavior", "detail": "길동이 병으로 세상을 떠났다", "original": "길동이 뇌성벽력과 오색운무 속에 백일승천하였다", "expected_flag": "character_agent"},
    60: {"field": "beat", "corruption": "character_trait", "detail": "길현이 평생 벼슬을 하지 못하였다", "original": "길현이 조선에서 승상까지 올라 영화를 누렸다", "expected_flag": "character_agent"},
}


def build_chapter_text(scenes: list[dict]) -> str:
    """Build prose text from one or two scene dicts."""
    parts: list[str] = []
    for s in scenes:
        parts.append(f"[장면] {s['title']}")
        parts.append(s["summary"])
        for beat in s["beats"]:
            parts.append(f"- {beat}")
        if s.get("location"):
            parts.append(f"[배경] {s['location']}")
        if len(scenes) > 1:
            parts.append("")  # blank line between merged scenes
    return "\n".join(parts)


def build_adversarial_text(clean_text: str, adv: dict) -> str:
    """Create adversarial version by appending the corrupted detail as a note."""
    return clean_text + f"\n[검증 주석] {adv['detail']}"


# Short name aliases → canonical name mapping for entity evaluation
CHARACTER_ALIASES: dict[str, list[str]] = {
    # 홍길동: 전 호칭 포괄 — 단명(길동), 율도국 왕 즉위 후(대왕, 율도대왕)
    "홍길동": ["길동", "길동이", "홍 길동", "대왕", "율도대왕", "율도 대왕", "율도왕 홍길동"],
    "홍 승상": ["승상", "대감", "홍 대감", "홍승상"],
    # 유씨 부인: 율도국 왕대비로 봉해진 후 호칭
    "유씨 부인": ["부인", "유씨", "정실 부인", "대비", "모비", "홍대비"],
    # 춘섬: 율도국 왕비·왕대비가 된 후 호칭
    "춘섬": ["춘섬이", "시비 춘섬", "왕대비", "왕대비(춘섬)", "모비"],
    "홍길현": ["길현", "길현이", "대감의 장자"],
    "초낭": ["곡산모", "초낭자", "초랑"],
    "관상녀": ["관상하는 계집", "상녀"],
    "이업": ["포도대장 이업"],
    "백소저": ["백씨", "백씨 중전", "소저"],
    "율도왕": ["율왕"],
    "맹춘": ["맹춘이"],
    "김인수": ["김 인수"],
    # 임금: 궁궐 씬에서 '전하', '상감' 등으로 호칭됨
    "임금": ["전하", "상감", "임금님"],
}


def merge_characters(scenes: list[dict]) -> list[str]:
    seen: list[str] = []
    for s in scenes:
        for c in s.get("characters", []):
            if c not in seen:
                seen.append(c)
    return seen


def merge_location(scenes: list[dict]) -> str:
    locs = [s.get("location", "") for s in scenes if s.get("location")]
    return locs[0] if locs else ""


def main() -> None:
    raw = json.loads(INPUT.read_text(encoding="utf-8"))
    scene_by_seq: dict[int, dict] = {s["seq"]: s for s in raw["scenes"]}

    # Verify mapping covers all 75 scenes exactly once
    all_scene_nums = []
    for ch_no, seqs in CHAPTER_MAP.items():
        all_scene_nums.extend(seqs)
    assert sorted(all_scene_nums) == list(range(1, 76)), (
        f"Mapping error: {sorted(all_scene_nums)}"
    )
    assert len(CHAPTER_MAP) == 60, f"Expected 60 chapters, got {len(CHAPTER_MAP)}"

    chapters: list[dict] = []
    for ch_no in sorted(CHAPTER_MAP.keys()):
        seqs = CHAPTER_MAP[ch_no]
        scenes = [scene_by_seq[s] for s in seqs]

        title = scenes[0]["title"] if len(scenes) == 1 else " / ".join(s["title"] for s in scenes)
        characters = merge_characters(scenes)
        location = merge_location(scenes)
        scene_text = build_chapter_text(scenes)

        gt = GROUND_TRUTH.get(ch_no, {})
        adv_info = ADVERSARIAL.get(ch_no, {})

        # Scale event range for merged chapters
        base_range = gt.get("event_count_range", [3, 20])
        if len(seqs) > 1:
            scale = len(seqs)
            event_range = [base_range[0], base_range[1] * scale]
        else:
            event_range = base_range

        # Build per-chapter aliases (only for characters in this chapter)
        ch_aliases = {
            c: aliases
            for c, aliases in CHARACTER_ALIASES.items()
            if c in characters
        }

        chapter = {
            "chapter": ch_no,
            "title": title,
            "source_scenes": seqs,
            "scene_text": scene_text,
            "characters": characters,
            "location": location,
            "ground_truth": {
                "expected_characters": characters,
                "forbidden_characters": [],
                "character_aliases": ch_aliases,
                "required_event_types": gt.get("required_event_types", []),
                "forbidden_event_types": gt.get("forbidden_event_types", []),
                "event_count_range": event_range,
                "expected_relationships": gt.get("expected_relationships", []),
                "pbkd_updates": gt.get("pbkd_updates", []),
                "expected_contradictions": gt.get("expected_contradictions", 0),
                "notes": gt.get("notes", ""),
            },
            "adversarial": {
                "scene_text": build_adversarial_text(scene_text, adv_info) if adv_info else scene_text,
                "corruption_type": adv_info.get("corruption", ""),
                "corrupted_detail": adv_info.get("detail", ""),
                "original_detail": adv_info.get("original", ""),
                "expected_flag_agent": adv_info.get("expected_flag", ""),
            } if adv_info else None,
        }
        chapters.append(chapter)

    canonical = {
        "title": "홍길동전 Canonical Dataset",
        "description": (
            "허균 홍길동전을 기반으로 한 NarrativeOS 평가 데이터셋.\n"
            "60챕터, 각 챕터마다 ground_truth (expected entities/events/PBKD) 및\n"
            "adversarial_test (의도적 오류 삽입 버전) 포함.\n"
            "Precision / Recall / FP / FN 측정용."
        ),
        "total_chapters": len(chapters),
        "source_scenes": 75,
        "characters": raw.get("characters", []),
        "evaluation_protocol": {
            "entity_precision": "detected_chars ∩ expected_chars / detected_chars",
            "entity_recall": "detected_chars ∩ expected_chars / expected_chars",
            "event_recall": "detected_required_event_types / required_event_types",
            "adversarial_tp": "contradiction detected in adversarial version",
            "adversarial_tn": "no contradiction in clean version",
        },
        "chapters": chapters,
    }

    OUTPUT.write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Canonical dataset saved → {OUTPUT}")
    print(f"   {len(chapters)} chapters, {sum(len(c['source_scenes']) for c in chapters)} source scenes")
    merge_count = sum(1 for c in chapters if len(c["source_scenes"]) > 1)
    print(f"   {merge_count} merged chapters (2 scenes → 1)")


if __name__ == "__main__":
    main()
