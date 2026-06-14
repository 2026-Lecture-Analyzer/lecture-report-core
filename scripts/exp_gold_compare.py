"""[실험] gold 검증 — 사람이 채점한 02-02 리포트(정답) vs RAG·holistic 항목별 일치도.

gold = 사람 평가 리포트(2026-02-02, 하루 전체) 18항목 점수. 파이프라인은 세션(오전/오후)
단위라, 두 방식 모두 **세션 점수를 항목별 평균내 day 단위로** 맞춘 뒤 gold와 비교(공정).

지표: MAE(평균절대오차, 낮을수록 정확) · 방향일치(±1 이내 비율) · 편향(평균 부호오차).

사용법:
    python -m scripts.exp_gold_compare --dir outputs/processed/_gold_0202
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from src.analyze.checklist import CATEGORIES, CHECKLIST

# 사람 채점(정답) 18항목(하루 전체). GOLDS[date] 로 등록, GOLD=기본(02-02, 하위호환).
GOLDS = {
    # docs 의 02-02 강의 품질 평가 리포트
    "2026-02-02": {
        "C1_repetition": 2, "C1_completeness": 3, "C1_consistency": 2,
        "C2_objective": 5, "C2_review": 5, "C2_order": 4, "C2_emphasis": 4, "C2_summary": 2,
        "C3_definition": 4, "C3_analogy": 4, "C3_prerequisite": 4, "C3_pace": 3,
        "C4_example": 4, "C4_practice": 4, "C4_error": 4,
        "C5_check": 3, "C5_engage": 3, "C5_answer": 3,
    },
    # gold #2 — docs/고도화/gold2_0206_초안_검토용.md 확정(검토자 승인 2026-06-14)
    "2026-02-06": {
        "C1_repetition": 2, "C1_completeness": 3, "C1_consistency": 2,
        "C2_objective": 2, "C2_review": 3, "C2_order": 3, "C2_emphasis": 3, "C2_summary": 2,
        "C3_definition": 4, "C3_analogy": 3, "C3_prerequisite": 3, "C3_pace": 3,
        "C4_example": 4, "C4_practice": 4, "C4_error": 3,
        "C5_check": 3, "C5_engage": 3, "C5_answer": 2,
    },
    # gold #3~5 — docs/고도화/gold_evidence_*.md 증거 기반(2026-06-14). 변별 극단 강의.
    # 02-23: 도입 명시적(목표·복습 5), 존댓말 최저 0.504
    "2026-02-23": {
        "C1_repetition": 2, "C1_completeness": 3, "C1_consistency": 2,
        "C2_objective": 4, "C2_review": 5, "C2_order": 4, "C2_emphasis": 3, "C2_summary": 3,
        "C3_definition": 4, "C3_analogy": 3, "C3_prerequisite": 4, "C3_pace": 3,
        "C4_example": 4, "C4_practice": 4, "C4_error": 3,
        "C5_check": 3, "C5_engage": 3, "C5_answer": 2,
    },
    # 02-25: 존댓말 최고 0.655(casual이 서술체 '했다/된다') → C1_consistency 3(변별 상단)
    "2026-02-25": {
        "C1_repetition": 2, "C1_completeness": 3, "C1_consistency": 3,
        "C2_objective": 3, "C2_review": 4, "C2_order": 3, "C2_emphasis": 3, "C2_summary": 2,
        "C3_definition": 4, "C3_analogy": 3, "C3_prerequisite": 4, "C3_pace": 3,
        "C4_example": 4, "C4_practice": 3, "C4_error": 3,
        "C5_check": 3, "C5_engage": 3, "C5_answer": 2,
    },
    # 02-26: cue 최저(이해확인 0.44/10분) → C5_check 2(변별 하단). 도입 명시적.
    "2026-02-26": {
        "C1_repetition": 2, "C1_completeness": 3, "C1_consistency": 2,
        "C2_objective": 4, "C2_review": 5, "C2_order": 4, "C2_emphasis": 3, "C2_summary": 2,
        "C3_definition": 4, "C3_analogy": 3, "C3_prerequisite": 4, "C3_pace": 3,
        "C4_example": 4, "C4_practice": 3, "C4_error": 3,
        "C5_check": 2, "C5_engage": 3, "C5_answer": 2,
    },
}
GOLD = {"date": "2026-02-02", "scores": GOLDS["2026-02-02"]}  # 하위호환(다른 스크립트 import)


def _day_avg(path: Path) -> dict[str, float]:
    """analysis.jsonl(세션별 행) → 항목별 day 평균 점수."""
    if not path.exists():
        return {}
    rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    acc: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if isinstance(r.get("score"), int):
            acc[r["item_key"]].append(r["score"])
    return {k: sum(v) / len(v) for k, v in acc.items()}


def _stats(gold: dict, pred: dict) -> dict:
    errs, signed, within1 = [], [], 0
    for k, g in gold.items():
        p = pred.get(k)
        if p is None:
            continue
        errs.append(abs(p - g))
        signed.append(p - g)
        if abs(p - g) <= 1:
            within1 += 1
    n = len(errs) or 1
    return {"mae": sum(errs) / n, "bias": sum(signed) / n,
            "within1": within1, "n": len(errs)}


def main() -> None:
    ap = argparse.ArgumentParser(description="gold(사람) vs RAG·Holistic·Hybrid 일치도")
    ap.add_argument("--dir", type=Path, default=Path("outputs/processed/_gold_0202"))
    ap.add_argument("--gold-date", default="2026-02-02", help=f"택1: {list(GOLDS)}")
    args = ap.parse_args()
    if args.gold_date not in GOLDS:
        raise SystemExit(f"gold 없음: {args.gold_date} (등록: {list(GOLDS)})")

    gold = GOLDS[args.gold_date]
    preds = {"RAG": _day_avg(args.dir / "analysis.jsonl"),
             "HOL": _day_avg(args.dir / "holistic_analysis.jsonl"),
             "HYB": _day_avg(args.dir / "hybrid_analysis.jsonl")}
    preds = {k: v for k, v in preds.items() if v}      # 존재하는 것만

    print("=" * 72)
    print(f"GOLD 검증 — {args.gold_date} 사람 채점 vs {' · '.join(preds)} (day 평균)")
    print("=" * 72)
    hdr = "  ".join(f"{k:>4}" for k in preds)
    print(f"{'item':16} {'GOLD':>4}  {hdr}")
    print("-" * 72)
    cat = {k: defaultdict(list) for k in ["GOLD", *preds]}
    for it in CHECKLIST:
        k = it["key"]; g = gold[k]
        cells = "  ".join(f"{(preds[p].get(k)):.1f}".rjust(4) if preds[p].get(k) is not None
                          else "   -" for p in preds)
        print(f"{k:16} {g:>4}  {cells}")
        cat["GOLD"][it["category"]].append(g)
        for p in preds:
            if preds[p].get(k) is not None:
                cat[p][it["category"]].append(preds[p][k])

    print("-" * 72)
    print("[카테고리 합계]")
    for c in CATEGORIES:
        cells = "  ".join(f"{p} {sum(cat[p][c]):>4.1f}" for p in preds)
        print(f"  {c} {CATEGORIES[c]:12} GOLD {sum(cat['GOLD'][c]):>3.0f}  {cells}")

    print("=" * 72)
    print(f"{'방식':10} {'MAE↓':>6} {'방향일치(±1)':>13} {'편향':>8}")
    for p in preds:
        s = _stats(gold, preds[p])
        print(f"{p:10} {s['mae']:>6.2f}   {s['within1']}/{s['n']} ({100*s['within1']//s['n']}%)  {s['bias']:>+7.2f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
