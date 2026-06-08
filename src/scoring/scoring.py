"""스코어링(⑦) — analysis.jsonl → scores.json. 규칙(결정적), LLM 안 씀.

설계(readme_V1): **항목별 가중**(checklist.weight high3/mid2/low1)으로 종합.
  항목 score(1~5) → 0~100 정규화 → 항목 가중 평균 → 카테고리·종합 강의력 점수.
  N/A(score=None)·부정증거(score 있음)는 정책대로 처리.

scores.json: {lectures:{lid:{date,session,category_scores,total_score,n_na,items}}, summary}
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.analyze.checklist import (CATEGORIES, SCORE_MAX, SCORE_MIN,
                                   WEIGHT_VALUE, by_key)


def load_analysis(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _norm(score_1_5: float) -> float:
    """1~5 → 0~100."""
    return (score_1_5 - SCORE_MIN) / (SCORE_MAX - SCORE_MIN) * 100


def score_lecture(rows: list[dict]) -> dict:
    """한 강의의 18항목 행 → 카테고리/종합 점수(항목 가중) + 항목별 상세."""
    items = by_key()
    cat_v: dict[str, float] = defaultdict(float)
    cat_w: dict[str, float] = defaultdict(float)
    tot_v = tot_w = 0.0
    n_na = 0
    detail: list[dict] = []

    for r in rows:
        key = r["item_key"]
        meta = items.get(key, {})
        s = r.get("score")
        w = WEIGHT_VALUE.get(meta.get("weight", "mid"), 2)
        if s is None:                       # N/A → 가중에서 제외
            n_na += 1
            detail.append({"item_key": key, "category": r["category"],
                           "score": None, "norm": None, "weight": w,
                           "negative": bool(r.get("routing", {}).get("negative_evidence"))})
            continue
        norm = _norm(float(s))
        cat = r["category"]
        cat_v[cat] += norm * w
        cat_w[cat] += w
        tot_v += norm * w
        tot_w += w
        detail.append({"item_key": key, "category": cat, "score": s,
                       "norm": round(norm, 1), "weight": w,
                       "negative": bool(r.get("routing", {}).get("negative_evidence"))})

    category_scores = {c: (round(cat_v[c] / cat_w[c], 1) if cat_w.get(c) else None)
                       for c in CATEGORIES}
    total_score = round(tot_v / tot_w, 1) if tot_w else None
    detail.sort(key=lambda d: d["item_key"])
    return {"category_scores": category_scores, "total_score": total_score,
            "n_na": n_na, "items": detail}


def compute_scores(analysis: list[dict]) -> dict:
    """전체 분석 → 강의별 점수 + 요약(평균·주차별 추이)."""
    per_lecture: dict[str, list[dict]] = defaultdict(list)
    for r in analysis:
        per_lecture[r["lecture_id"]].append(r)

    lectures: dict[str, dict] = {}
    for lid, rows in per_lecture.items():
        s = score_lecture(rows)
        s.update(date=rows[0]["date"], session=rows[0]["session"])
        lectures[lid] = s

    totals = [v["total_score"] for v in lectures.values() if v["total_score"] is not None]
    by_date = defaultdict(list)               # 주차/일자 추이용
    for lid, v in lectures.items():
        if v["total_score"] is not None:
            by_date[v["date"]].append(v["total_score"])
    trend = {d: round(sum(xs) / len(xs), 1) for d, xs in sorted(by_date.items())}

    summary = {
        "n_lectures": len(lectures),
        "avg_total": round(sum(totals) / len(totals), 1) if totals else None,
        "by_date": trend,
    }
    return {"lectures": lectures, "summary": summary}


def save_scores(scores: dict, out_path: Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_path)


def run_scoring(analysis_path: Path, out_path: Path, log=print) -> dict:
    """analysis.jsonl → scores.json."""
    scores = compute_scores(load_analysis(analysis_path))
    save_scores(scores, out_path)
    log(f"[⑦ 스코어링] 강의 {scores['summary']['n_lectures']}편, "
        f"평균 {scores['summary']['avg_total']}점 → {out_path}")
    return scores
