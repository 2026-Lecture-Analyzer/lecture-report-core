"""스코어링(P3) — analysis.jsonl → scores.json.

담당: P3 (스코어링·검증)
개발할 것: 18항목 평가 → 카테고리 평균 → 가중합 → 0~100 종합 강의력 점수.
           강사/세션 비교, 주차별 추이. 점수 계산은 규칙(결정적), LLM 안 씀.
입력 → 출력: analysis.jsonl(또는 dict 리스트) → scores.json
참고: docs/SCHEMA.md(scores.json), src/analyze/checklist.py(CATEGORIES, 1~5 척도)
"""
from __future__ import annotations

from pathlib import Path

from src.analyze.checklist import CATEGORIES, SCORE_MAX, SCORE_MIN  # noqa: F401

# TODO(P3): CATEGORY_WEIGHTS 확정 — 현재 균등. 팀 합의/체크리스트 v3 배점 반영.
CATEGORY_WEIGHTS = {c: 1 / len(CATEGORIES) for c in CATEGORIES}


def load_analysis(path: Path) -> list[dict]:
    """analysis.jsonl 로드."""
    # TODO(P3): analysis.jsonl 한 줄씩 json.loads 해서 리스트 반환
    raise NotImplementedError("P3: 구현 필요")


def score_lecture(rows: list[dict]) -> dict:
    """한 강의의 18항목 행 → {category_scores, total_score} (0~100)."""
    # TODO(P3): 카테고리별 항목 점수 평균(1~5)
    # TODO(P3): 카테고리 가중합 → 0~100 정규화(_norm)
    # TODO(P3): 결측(score=None) 처리 정책 확정(제외 평균? 0점?)
    # 참고 구현: 파일 하단 주석
    raise NotImplementedError("P3: 구현 필요 — 아래 참고 구현 참조")


def compute_scores(analysis: list[dict]) -> dict:
    """전체 분석 → 강의별/강사별/주차별 점수 묶음."""
    # TODO(P3): lecture_id 별로 묶어 score_lecture 적용
    # TODO(P3): (확장) 강사별 집계, 주차별 시계열 추이
    raise NotImplementedError("P3: 구현 필요")


def save_scores(scores: dict, out_path: Path) -> str:
    """scores.json 저장."""
    # TODO(P3): json.dump(indent=2, ensure_ascii=False) 로 저장
    raise NotImplementedError("P3: 구현 필요")


# ════════════════════════════════════════════════════════════════════════
# 참고 구현 (Claude 초안 — 지우고 직접 작성하세요)
# ════════════════════════════════════════════════════════════════════════
# import json
# from collections import defaultdict
#
# def load_analysis(path):
#     with Path(path).open(encoding="utf-8") as f:
#         return [json.loads(line) for line in f if line.strip()]
#
# def _norm(score_1_5):           # 1~5 → 0~100
#     return (score_1_5 - SCORE_MIN) / (SCORE_MAX - SCORE_MIN) * 100
#
# def score_lecture(rows):
#     by_cat = defaultdict(list)
#     for r in rows:
#         if r.get("score") is not None:
#             by_cat[r["category"]].append(float(r["score"]))
#     cat_scores = {c: (sum(by_cat[c]) / len(by_cat[c]) if by_cat.get(c) else None)
#                   for c in CATEGORIES}
#     avail = {c: s for c, s in cat_scores.items() if s is not None}
#     wsum = sum(CATEGORY_WEIGHTS[c] for c in avail) or 1
#     total_1_5 = sum(s * CATEGORY_WEIGHTS[c] for c, s in avail.items()) / wsum
#     return {
#         "category_scores": {c: (round(_norm(s), 1) if s is not None else None)
#                             for c, s in cat_scores.items()},
#         "total_score": round(_norm(total_1_5), 1) if avail else None,
#     }
#
# def compute_scores(analysis):
#     per_lecture = defaultdict(list)
#     for r in analysis:
#         per_lecture[r["lecture_id"]].append(r)
#     lectures = {}
#     for lid, rows in per_lecture.items():
#         s = score_lecture(rows)
#         s.update(date=rows[0]["date"], session=rows[0]["session"])
#         lectures[lid] = s
#     return {"lectures": lectures}
#
# def save_scores(scores, out_path):
#     Path(out_path).parent.mkdir(parents=True, exist_ok=True)
#     Path(out_path).write_text(json.dumps(scores, ensure_ascii=False, indent=2),
#                               encoding="utf-8")
#     return str(out_path)
