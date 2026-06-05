"""강의 품질 평가 체크리스트 — 5개 카테고리 · 18개 항목 (분석 엔진의 진실원천).

출처: 제공 데이터 `강의품질평가체크리스트_v3`(README 요약 기준). 실제 PDF/DOCX에
세부 기준이 더 있으면 description 을 그 문구로 교체할 것(데이터는 git 미포함이라
여기엔 요약만 둔다).

각 항목:
    key        : 안정적 식별자(스키마/집계용, 변경 금지)
    category   : 5개 카테고리 중 하나
    title      : 사람이 읽는 항목명
    description: LLM 평가 프롬프트에 들어갈 판정 기준
"""
from __future__ import annotations

CATEGORIES = {
    "C1": "언어 표현 품질",
    "C2": "강의 도입 및 구조",
    "C3": "개념 설명 명확성",
    "C4": "예시 및 실습 연계",
    "C5": "수강생 상호작용",
}

# 18개 항목 (3+5+4+3+3)
CHECKLIST = [
    # C1 언어 표현 품질 (3)
    {"key": "C1_repetition", "category": "C1", "title": "불필요한 반복 표현",
     "description": "군더더기·간투사(이제, 저희가, 그다음에, 막, 뭐 등)의 과도한 반복 없이 간결하게 말하는가."},
    {"key": "C1_completeness", "category": "C1", "title": "발화 완결성",
     "description": "문장이 중간에 끊기거나 흐지부지되지 않고 의미가 완결되는가."},
    {"key": "C1_consistency", "category": "C1", "title": "언어 일관성",
     "description": "용어·호칭·문체가 일관되게 유지되는가."},
    # C2 강의 도입 및 구조 (5)
    {"key": "C2_objective", "category": "C2", "title": "학습 목표 안내",
     "description": "수업 시작 시 오늘 배울 목표/범위를 명확히 안내하는가."},
    {"key": "C2_review", "category": "C2", "title": "전날 복습 연계",
     "description": "이전 차시 내용을 환기하며 연결하는가."},
    {"key": "C2_order", "category": "C2", "title": "설명 순서",
     "description": "내용 전개 순서가 논리적이고 따라가기 쉬운가."},
    {"key": "C2_emphasis", "category": "C2", "title": "핵심 강조",
     "description": "중요한 개념을 분명히 강조해 주는가."},
    {"key": "C2_summary", "category": "C2", "title": "마무리 요약",
     "description": "수업 끝에 핵심을 요약·정리하는가."},
    # C3 개념 설명 명확성 (4)
    {"key": "C3_definition", "category": "C3", "title": "개념 정의",
     "description": "새 개념을 정확하고 이해 가능한 말로 정의하는가."},
    {"key": "C3_analogy", "category": "C3", "title": "비유/예시 활용",
     "description": "적절한 비유나 예시로 이해를 돕는가."},
    {"key": "C3_prerequisite", "category": "C3", "title": "선행 개념 확인",
     "description": "필요한 선행 지식을 짚어주거나 확인하는가."},
    {"key": "C3_pace", "category": "C3", "title": "발화 속도 적절성",
     "description": "말의 속도/밀도가 이해하기에 적절한가."},
    # C4 예시 및 실습 연계 (3)
    {"key": "C4_example", "category": "C4", "title": "예시 적절성",
     "description": "예시가 개념과 잘 맞고 도움이 되는가."},
    {"key": "C4_practice", "category": "C4", "title": "실습 연계",
     "description": "설명을 실습/코드와 연결해 적용하게 하는가."},
    {"key": "C4_error", "category": "C4", "title": "오류 대응",
     "description": "에러/문제 상황을 잘 짚고 해결 과정을 보여주는가."},
    # C5 수강생 상호작용 (3)
    {"key": "C5_check", "category": "C5", "title": "이해 확인 질문",
     "description": "이해 여부를 확인하는 질문을 던지는가."},
    {"key": "C5_engage", "category": "C5", "title": "참여 유도",
     "description": "수강생의 참여·반응을 유도하는가."},
    {"key": "C5_answer", "category": "C5", "title": "질문 응답 충분성",
     "description": "수강생 질문에 충분히 답하는가."},
]

assert len(CHECKLIST) == 18, "체크리스트는 18개 항목이어야 함"

# 점수 척도 (1~5). 분석/스코어링 공통 기준.
SCORE_MIN, SCORE_MAX = 1, 5


def by_key() -> dict[str, dict]:
    return {item["key"]: item for item in CHECKLIST}


def by_category() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for item in CHECKLIST:
        out[item["category"]].append(item)
    return out
