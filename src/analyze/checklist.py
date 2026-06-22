"""강의 품질 평가 체크리스트 — 5개 카테고리 · 18개 항목 (분석 엔진의 진실원천).

출처: 제공 데이터 `new_강의 품질 기준.pdf`. 각 항목에 PDF의 **세부기준(description)**·
**가중치(weight)** 를 그대로 반영하고, KYS 설계(§3, §9)에서 도출한 **평가 유형(eval_type)**·
**시드 키워드(seed_keywords)** 를 같이 박았다.

※ 신(新) 기준 변경점(구 기준 대비):
    - 카테고리 재편: C2 강의 구조 · C4 진행 방식 · C5 실습 및 적용
    - 삭제: 오류 대응 · 이해 확인 질문 · 참여 유도 · 질문 응답 충분성
    - 추가: 용어 설명 충분성 · 개념 간 연결성 · 코드 설명 충실성 · 학습 전환 안내
    - 이동: 발화 속도(C3→C4) · 예시 적절성/실습 연계(C4→C5)
    - 가중치 변경(PDF): 전날 복습 연계 중간 · 설명 구조성 높음 · 선행 개념 확인 높음

각 항목 필드:
    key          : 안정적 식별자(스키마/집계용, 변경 금지)
    category     : 5개 카테고리 중 하나
    title        : 사람이 읽는 항목명
    description  : LLM 평가 프롬프트에 들어갈 판정 기준(PDF 세부기준)
    weight       : "high" | "mid" | "low"  (PDF 가중치 높음/중간/낮음)
    eval_type    : 평가 라우팅 유형
                   "metric" 지표계산 · "intro" 도입부 · "outro" 종료부
                   "local" 국소-분산(검색·태깅) · "global" 전역
    needs_student: 학생 발화가 있어야 평가 가능(없으면 N/A). 제공 데이터는 단일화자
                   (config.SINGLE_SPEAKER)라 현재 전 항목 False.
    seed_keywords: 고정밀 cue. 태깅 검색에서 floor 구제(저sim 진짜 인스턴스 살림) +
                   랭킹 가산점. 동음이의·기술homonym(실행/오류/따라 등)은 넣지 않는다.
"""
from __future__ import annotations

CATEGORIES = {
    "C1": "언어 표현 품질",
    "C2": "강의 구조",
    "C3": "개념 설명 명확성",
    "C4": "진행 방식",
    "C5": "실습 및 적용",
}

WEIGHT_VALUE = {"high": 3, "mid": 2, "low": 1}  # P3 가중 스코어링용

# 18개 항목 (3+5+6+2+2)
CHECKLIST = [
    # ── C1 언어 표현 품질 ──
    {"key": "C1_repetition", "category": "C1", "title": "반복 표현",
     "description": ("동일 단어, 문장 또는 특정 접속어(예: '이제', '그래서')를 "
                     "과도하게 반복하지 않는가."),
     "weight": "high", "eval_type": "metric", "needs_student": False,
     "seed_keywords": ["이제", "그래서", "그러면", "막", "뭐", "좀", "이렇게"]},
    {"key": "C1_completeness", "category": "C1", "title": "발화 완결성",
     "description": "문장이 중간에 끊기지 않고 완결된 형태로 마무리되는가.",
     "weight": "mid", "eval_type": "global", "needs_student": False,
     "seed_keywords": []},
    {"key": "C1_consistency", "category": "C1", "title": "언어 일관성",
     "description": "존댓말/반말 등 화법이 강의 전반에 걸쳐 일관되게 유지되는가.",
     "weight": "mid", "eval_type": "global", "needs_student": False,
     "seed_keywords": []},
    # ── C2 강의 구조 ──
    {"key": "C2_objective", "category": "C2", "title": "학습 목표 안내",
     "description": "강의 시작 시 오늘 학습할 내용, 목표, 진행 순서를 명확하게 안내하는가.",
     "weight": "high", "eval_type": "intro", "needs_student": False,
     "seed_keywords": ["오늘", "목표", "배울", "진행", "할 거", "하겠습니다"]},
    {"key": "C2_review", "category": "C2", "title": "전날 복습 연계",
     "description": ("이전 강의 내용을 간략히 복습하고 오늘 학습 내용과 자연스럽게 "
                     "연결하는가."),
     "weight": "mid", "eval_type": "intro", "needs_student": False,
     "seed_keywords": ["지난 시간", "저번", "복습", "어제", "앞에서", "지난번", "지난주"]},
    {"key": "C2_structure", "category": "C2", "title": "설명 구조성",
     "description": ("개념, 예시, 실습 등이 체계적인 흐름으로 구성되어 이해하기 쉽게 "
                     "전달되는가."),
     "weight": "high", "eval_type": "global", "needs_student": False,
     "seed_keywords": []},
    {"key": "C2_emphasis", "category": "C2", "title": "핵심 내용 강조",
     "description": "중요한 개념이나 실무적으로 중요한 내용을 반복 또는 강조하여 전달하는가.",
     "weight": "mid", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["중요", "꼭", "반드시", "핵심", "기억", "포인트"]},
    {"key": "C2_summary", "category": "C2", "title": "마무리 요약",
     "description": "강의 종료 시 핵심 내용을 요약하고 정리하는가.",
     "weight": "low", "eval_type": "outro", "needs_student": False,
     "seed_keywords": ["정리", "요약", "오늘 배운", "마무리", "정리하면"]},
    # ── C3 개념 설명 명확성 ──
    {"key": "C3_definition", "category": "C3", "title": "개념 정의",
     "description": "새로운 핵심 개념 등장 시 명확하고 이해하기 쉽게 정의하는가.",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["이란", "정의", "라고 합니다", "라고 해", "의미"]},
    {"key": "C3_term_explanation", "category": "C3", "title": "용어 설명 충분성",
     "description": ("전문 용어나 기술 용어를 설명 없이 사용하지 않고 적절한 해설을 "
                     "제공하는가."),
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["용어", "줄여서", "약자", "라는 게", "라는 건", "뜻"]},
    {"key": "C3_analogy", "category": "C3", "title": "비유 및 예시 활용",
     "description": ("어려운 개념을 설명하기 위해 적절한 비유, 사례, 실생활 예시를 "
                     "활용하는가."),
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["예를 들어", "비유", "마치", "처럼", "쉽게 말하", "실생활"]},
    {"key": "C3_prerequisite", "category": "C3", "title": "선행 개념 확인",
     "description": "선행 개념 설명 없이 갑작스럽게 심화 내용으로 넘어가지 않는가.",
     "weight": "high", "eval_type": "global", "needs_student": False,
     "seed_keywords": []},
    {"key": "C3_concept_connection", "category": "C3", "title": "개념 간 연결성",
     "description": "현재 개념을 이전에 학습한 개념과 연결하여 설명하는가.",
     "weight": "mid", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["연결", "관련", "이어서", "마찬가지로", "연관", "관계"]},
    {"key": "C3_code_explanation", "category": "C3", "title": "코드 설명 충실성",
     "description": "코드의 동작뿐 아니라 작성 이유와 의도를 함께 설명하는가.",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["코드", "이 줄", "왜 이렇게", "의도", "이 부분은"]},
    # ── C4 진행 방식 ──
    {"key": "C4_pace", "category": "C4", "title": "발화 속도 적절성",
     "description": "타임스탬프 기준 분당 발화량이 수강생이 따라가기 적절한 수준인가.",
     "weight": "mid", "eval_type": "metric", "needs_student": False,
     "seed_keywords": []},
    {"key": "C4_transition", "category": "C4", "title": "학습 전환 안내",
     "description": ("주제 변경 또는 새로운 챕터 진입 시 전환 멘트를 통해 흐름을 "
                     "안내하는가."),
     "weight": "mid", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["넘어가", "다음으로", "이번에는", "이어서", "정리하고", "다음 챕터"]},
    # ── C5 실습 및 적용 ──
    {"key": "C5_example", "category": "C5", "title": "예시 적절성",
     "description": ("예시가 학습 수준에 적합하며 실제 업무 또는 실무 상황과 관련성이 "
                     "있는가."),
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["예시", "실무", "현업", "사례", "예로"]},
    {"key": "C5_practice", "category": "C5", "title": "실습 연계",
     "description": "이론 설명 후 실습이나 적용 과정으로 자연스럽게 연결되는가.",
     "weight": "high", "eval_type": "local", "needs_student": False,
     "seed_keywords": ["실습", "연습", "해보", "해 보", "풀어", "쳐보", "확인해 보",
                       "직접 해", "따라 해", "테스트해"]},  # 행동 특화(broad한 직접/따라/입력 제외)
]

assert len(CHECKLIST) == 18, "체크리스트는 18개 항목이어야 함"

# 점수 척도 (1~5). 분석/스코어링 공통 기준.
SCORE_MIN, SCORE_MAX = 1, 5

# 항목별 exemplar — 태깅(⑤) 쿼리 임베딩용 '실제 발화처럼 들리는 예시' 문장(RubricRAG식).
# description(추상 기준문)은 구어체 청크와 코사인이 낮아 변별이 안 됨(sim 0.35~0.40).
# exemplar 평균 임베딩으로 쿼리하면 변별폭 +71%·오탐↓(휴식공지·UI가 실습연계로 안 잡힘).
# A/B 검증: 2026-02-05. 항목 추가/수정 시 '그 항목이 강의에서 이렇게 들린다'는 발화체로.
ITEM_EXEMPLARS = {
    "C2_objective": ["오늘은 SELECT 문의 전체 실행 흐름을 배워보겠습니다.",
                     "이번 시간에는 조인과 서브쿼리를 다룰 예정입니다.",
                     "오늘 학습 목표는 트랜잭션 개념을 이해하는 것입니다."],
    "C2_review": ["지난 시간에 우리가 기본 SELECT 문을 배웠죠.",
                  "어제 배운 워크벤치 활용 기억나시나요.",
                  "앞에서 다룬 데이터 타입과 이어집니다."],
    "C2_emphasis": ["이 부분은 시험에 반드시 출제되니 꼭 기억하세요.",
                    "여기서 가장 중요한 건 무결성 제약 조건입니다.",
                    "이건 정말 핵심이니까 다시 한번 강조합니다."],
    "C2_summary": ["오늘 배운 내용을 정리하면 SELECT, WHERE, GROUP BY입니다.",
                   "마무리로 핵심만 다시 짚어보겠습니다.",
                   "정리하면 트랜잭션은 ACID 속성을 가집니다."],
    "C3_definition": ["무결성이란 데이터의 정확성과 일관성을 유지하는 규칙을 말합니다.",
                      "기본키는 행을 유일하게 식별하는 컬럼입니다.",
                      "트랜잭션이란 하나의 논리적 작업 단위를 의미합니다."],
    "C3_term_explanation": ["NULL은 값이 없음을 나타내는 특별한 상태입니다.",
                            "AUTO_INCREMENT는 자동으로 번호를 증가시키는 속성입니다.",
                            "외래키는 다른 테이블을 참조하는 컬럼을 뜻합니다."],
    "C3_analogy": ["클래스에서 속성과 메소드를 정의하듯 테이블은 컬럼과 로우로 구성됩니다.",
                   "예를 들어 몽고DB는 대규모 사용자 관리에 활용됩니다.",
                   "마치 엑셀 시트처럼 행과 열로 데이터를 저장합니다."],
    "C3_concept_connection": ["앞에서 배운 기본키 개념이 여기 외래키와 연결됩니다.",
                              "이전에 다룬 SELECT가 이 서브쿼리 안에서도 쓰입니다.",
                              "조금 전 정의한 트랜잭션을 격리 수준과 함께 보면 됩니다."],
    "C3_code_explanation": ["이 쿼리는 WHERE 절로 부서 번호를 필터링하려고 이렇게 작성합니다.",
                            "여기서 GROUP BY를 먼저 쓰는 이유는 집계 단위를 정하기 위해서입니다.",
                            "이 조인을 LEFT로 쓰는 건 한쪽 데이터를 모두 살리려는 의도입니다."],
    "C4_transition": ["자 이제 다음 주제인 서브쿼리로 넘어가겠습니다.",
                      "여기까지 이론이었고 이제 실습으로 넘어가죠.",
                      "그럼 화면을 전환해서 다음 내용을 보겠습니다."],
    "C5_example": ["예를 들어 사용자 연락처에서 핸드폰이 없으면 집 전화를 씁니다.",
                   "실무에서는 주문 테이블과 회원 테이블을 조인해서 씁니다.",
                   "현업에서 우편번호나 좌표 같은 복합 속성을 자주 다룹니다."],
    "C5_practice": ["자 여러분도 직접 한번 해보세요.",
                    "이 도구로 직접 테스트해 보시면 됩니다.",
                    "이론을 봤으니 이제 직접 실습으로 해봅시다.",
                    "가격 계산기 페이지에 들어가서 직접 입력해 보세요.",
                    "버추얼박스 같은 환경에서 직접 구성해 볼 수 있습니다.",
                    "직접 SELECT 쿼리를 실행해 보겠습니다."],
}


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
