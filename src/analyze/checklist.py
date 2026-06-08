"""강의 품질 평가 체크리스트 — 5개 카테고리 · 18개 항목 (분석 엔진의 진실원천).

출처: 제공 데이터 `강의 품질 기준.pdf`(ver 2.0). 각 항목에 PDF의 **가중치**와,
KYS 설계(§3, §9)에서 도출한 **평가 유형(eval_type)** · **시드 키워드(seed_keywords)** 를
같이 박았다.

각 항목 필드:
    key          : 안정적 식별자(스키마/집계용, 변경 금지)
    category     : 5개 카테고리 중 하나
    title        : 사람이 읽는 항목명
    description  : LLM 평가 프롬프트에 들어갈 판정 기준(PDF 세부기준)
    weight       : "high" | "mid" | "low"  (PDF 가중치 높음/중간/낮음)
    eval_type    : 평가 라우팅 유형
                   "metric" 지표계산 · "intro" 도입부 · "outro" 종료부
                   "local" 국소-분산(검색·태깅) · "global" 전역
    needs_student: 학생 발화가 있어야 평가 가능(없으면 N/A)
    seed_keywords: 룰 태깅용 시드(임베딩과 병행). 약한 신호로 취급.
"""
from __future__ import annotations

CATEGORIES = {
    "C1": "언어 표현 품질",
    "C2": "강의 도입 및 구조",
    "C3": "개념 설명 명확성",
    "C4": "예시 및 실습 연계",
    "C5": "수강생 상호작용",
}

WEIGHT_VALUE = {"high": 3, "mid": 2, "low": 1}  # P3 가중 스코어링용

# 18개 항목 (3+5+4+3+3)
CHECKLIST = [
    # ── C1 언어 표현 품질 ──
    {"key": "C1_repetition", "category": "C1", "title": "불필요한 반복 표현",
     "description": "동일 단어/문장 및 '이제','그래서' 등 특정 표현을 과도하게 반복하지 않는가.",
     "weight": "high", "eval_type": "metric", "needs_student": False,
     "seed_keywords": ["이제", "그래서", "그러면", "막", "뭐", "좀", "이렇게"]},
    {"key": "C1_completeness", "category": "C1", "title": "발화 완결성",
     "description": "문장이 완결된 형태로 끝맺음되는가(중간에 끊기지 않는가).",
     "weight": "mid", "eval_type": "global", "needs_student": False,
     "seed_keywords": []},
    {"key": "C1_consistency", "category": "C1", "title": "언어 일관성",
     "description": "강의 전반에 걸쳐 존댓말/반말이 일관되게 사용되는가.",
     "weight": "mid", "eval_type": "global", "needs_student": False,
     "seed_keywords": []},
    # ── C2 강의 도입 및 구조 ──
    {"key": "C2_objective", "category": "C2", "title": "학습 목표 안내",
     "description": "강의 시작 시 오늘의 학습 목표와 진행 순서를 명확히 안내하는가.",
     "weight": "high", "eval_type": "intro", "needs_student": False,
     "seed_keywords": ["오늘", "목표", "배울", "진행", "순서", "할 거", "하겠습니다"]},
    {"key": "C2_review", "category": "C2", "title": "전날 복습 연계",
     "description": "이전 강의 내용을 간략히 복습하고 오늘 내용과 연결하는가.",
     "weight": "high", "eval_type": "intro", "needs_student": False,
     "seed_keywords": ["지난 시간", "저번", "복습", "어제", "앞에서", "지난번", "지난주"]},
    {"key": "C2_order", "category": "C2", "title": "설명 순서",
     "description": "개념→예시→실습의 순서로 구조적으로 설명하는가.",
     "weight": "mid", "eval_type": "global", "needs_student": False,
     "seed_keywords": []},
    {"key": "C2_emphasis", "category": "C2", "title": "핵심 내용 강조",
     "description": "중요한 내용을 반복하거나 강조하여 전달하는가.",
     "weight": "mid", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["중요", "꼭", "반드시", "핵심", "기억", "포인트"]},
    {"key": "C2_summary", "category": "C2", "title": "마무리 요약",
     "description": "강의 마무리 시 핵심 내용을 요약 정리하는가.",
     "weight": "low", "eval_type": "outro", "needs_student": False,
     "seed_keywords": ["정리", "요약", "오늘 배운", "마무리", "정리하면"]},
    # ── C3 개념 설명 명확성 ──
    {"key": "C3_definition", "category": "C3", "title": "개념 정의",
     "description": "핵심 개념을 처음 등장 시 명확하게 정의하는가.",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["란", "이란", "정의", "라고 합니다", "라고 해", "의미", "개념"]},
    {"key": "C3_analogy", "category": "C3", "title": "비유 및 예시 활용",
     "description": "어려운 개념에 적절한 비유나 실생활 예시를 활용하는가.",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["예를 들어", "비유", "마치", "처럼", "쉽게 말하", "실생활"]},
    {"key": "C3_prerequisite", "category": "C3", "title": "선행 개념 확인",
     "description": "선행 개념 없이 갑자기 심화 내용으로 넘어가지 않는가.",
     "weight": "mid", "eval_type": "global", "needs_student": False,
     "seed_keywords": []},
    {"key": "C3_pace", "category": "C3", "title": "발화 속도 적절성",
     "description": "타임스탬프 기준 분당 발화량이 수강생이 따라가기 적절한 수준인가.",
     "weight": "mid", "eval_type": "metric", "needs_student": False,
     "seed_keywords": []},
    # ── C4 예시 및 실습 연계 ──
    {"key": "C4_example", "category": "C4", "title": "예시 적절성",
     "description": "예시가 강의 수준 및 실제 업무 현장과 연관성이 있는가.",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["예시", "실무", "현업", "실제", "사례", "예로"]},
    {"key": "C4_practice", "category": "C4", "title": "실습 연계",
     "description": "이론 설명 후 실습으로 자연스럽게 연결되는가.",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["실습", "해보", "직접", "따라", "코드", "쳐보", "실행"]},
    {"key": "C4_error", "category": "C4", "title": "오류 대응",
     "description": "실습 중 발생하는 오류나 질문에 적절히 대응하는가.",
     "weight": "mid", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["오류", "에러", "안 돼", "안돼", "왜 안", "버그", "틀렸"]},
    # ── C5 수강생 상호작용 ──
    {"key": "C5_check", "category": "C5", "title": "이해 확인 질문",
     "description": "수강생의 이해 여부를 확인하는 질문을 적절히 하는가('되셨어요?','이해하셨나요?' 등).",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["되셨어요", "이해하셨", "아시겠", "맞죠", "괜찮으세요", "되시나요"]},
    {"key": "C5_engage", "category": "C5", "title": "참여 유도",
     "description": "일방적 설명이 아닌 수강생의 직접 참여(풀어보기, 확인 등)를 유도하는가.",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["해보세요", "풀어", "직접 해", "해볼까요", "같이", "나와서"]},
    {"key": "C5_answer", "category": "C5", "title": "질문 응답 충분성",
     "description": "수강생 질문에 명확하고 충분하게 답변하는가.",
     "weight": "high", "eval_type": "local", "needs_student": True,
     "seed_keywords": ["질문", "여쭤", "물어", "답변"]},
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


def taggable_items() -> list[dict]:
    """chunk 태깅(키워드+임베딩) 대상 = 국소/도입/종료 유형만.

    metric·global 은 chunk 태깅이 아니라 지표·전역 뷰로 평가하므로 제외(§5).
    """
    return [it for it in CHECKLIST if it["eval_type"] in ("local", "intro", "outro")]


def items_by_eval_type() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for it in CHECKLIST:
        out.setdefault(it["eval_type"], []).append(it)
    return out
