"""대시보드 공용 상수 — 체크리스트 18항목 메타·카테고리·색상."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

CAT_NAME = {"C1": "언어표현품질", "C2": "강의구조", "C3": "개념설명명확성",
            "C4": "진행방식", "C5": "실습·적용"}
CATS = ["C1", "C2", "C3", "C4", "C5"]

CAT_COLORS = {"C1": "#6366f1", "C2": "#0ea5e9", "C3": "#10b981", "C4": "#f59e0b", "C5": "#ec4899"}
SCORE_COLOR = {5: "#059669", 4: "#34d399", 3: "#f59e0b", 2: "#f97316", 1: "#ef4444"}

# 항목 메타 — (한글명, 평가 설명). 체크리스트 v5 18항목.
ITEM_META = {
    "C1_repetition": ("반복 표현", "동일 단어·문장·접속어('이제·그래서')를 과도하게 반복하지 않는가."),
    "C1_completeness": ("발화 완결성", "문장이 중간에 끊기지 않고 완결된 형태로 마무리되는가."),
    "C1_consistency": ("언어 일관성", "존댓말/반말 등 화법이 강의 전반에 일관되게 유지되는가."),
    "C2_objective": ("학습 목표 안내", "강의 시작 시 오늘 배울 내용·목표·진행 순서를 명확히 안내하는가."),
    "C2_review": ("전날 복습 연계", "이전 강의 내용을 간략히 복습하고 오늘 내용과 자연스럽게 연결하는가."),
    "C2_structure": ("설명 구조성", "개념·예시·실습이 체계적 흐름으로 구성되어 이해하기 쉬운가."),
    "C2_emphasis": ("핵심 내용 강조", "중요한 개념·실무 포인트를 반복·강조하여 전달하는가."),
    "C2_summary": ("마무리 요약", "강의 종료 시 핵심 내용을 요약·정리하는가."),
    "C3_definition": ("개념 정의", "새 핵심 개념 등장 시 명확하고 이해하기 쉽게 정의하는가."),
    "C3_term_explanation": ("용어 설명 충분성", "전문·기술 용어를 설명 없이 쓰지 않고 적절히 해설하는가."),
    "C3_analogy": ("비유 및 예시 활용", "어려운 개념에 적절한 비유·사례·실생활 예시를 활용하는가."),
    "C3_prerequisite": ("선행 개념 확인", "선행 개념 설명 없이 갑자기 심화로 넘어가지 않는가."),
    "C3_concept_connection": ("개념 간 연결성", "현재 개념을 이전 학습 개념과 연결하여 설명하는가."),
    "C3_code_explanation": ("코드 설명 충실성", "코드 동작뿐 아니라 작성 이유·의도를 함께 설명하는가."),
    "C4_pace": ("발화 속도 적절성", "타임스탬프 기준 분당 발화량이 따라가기 적절한가."),
    "C4_transition": ("학습 전환 안내", "주제 변경·새 챕터 진입 시 전환 멘트로 흐름을 안내하는가."),
    "C5_example": ("예시 적절성", "예시가 학습 수준에 맞고 실무·실생활과 관련 있는가."),
    "C5_practice": ("실습 연계", "이론 설명 후 실습·적용으로 자연스럽게 연결하는가."),
}
ITEM_ORDER = list(ITEM_META)


def cat_avg(item_scores: dict) -> dict:
    """{item_key: score} → {C1..C5: 평균 or None}."""
    by = defaultdict(list)
    for k, v in item_scores.items():
        if isinstance(v, (int, float)):
            by[k.split("_")[0]].append(v)
    return {c: round(mean(by[c]), 2) if by.get(c) else None for c in CATS}
