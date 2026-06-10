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

# 사람 채점(정답) — docs 의 02-02 강의 품질 평가 리포트 18항목(하루 전체).
GOLD = {
    "date": "2026-02-02",
    "scores": {
        "C1_repetition": 2, "C1_completeness": 3, "C1_consistency": 2,
        "C2_objective": 5, "C2_review": 5, "C2_order": 4, "C2_emphasis": 4, "C2_summary": 2,
        "C3_definition": 4, "C3_analogy": 4, "C3_prerequisite": 4, "C3_pace": 3,
        "C4_example": 4, "C4_practice": 4, "C4_error": 4,
        "C5_check": 3, "C5_engage": 3, "C5_answer": 3,
    },
}


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
    ap = argparse.ArgumentParser(description="gold(사람) vs RAG·holistic 일치도")
    ap.add_argument("--dir", type=Path, default=Path("outputs/processed/_gold_0202"))
    args = ap.parse_args()

    gold = GOLD["scores"]
    rag = _day_avg(args.dir / "analysis.jsonl")
    hol = _day_avg(args.dir / "holistic_analysis.jsonl")

    print("=" * 76)
    print(f"GOLD 검증 — {GOLD['date']} 사람 채점 vs RAG · Holistic (day 평균)")
    print("=" * 76)
    print(f"{'item':16} {'type':7} {'GOLD':>4} {'RAG':>5} {'HOL':>5}  {'|RAG-G|':>7} {'|HOL-G|':>7}  승")
    print("-" * 76)
    cat_g, cat_r, cat_h = defaultdict(list), defaultdict(list), defaultdict(list)
    for it in CHECKLIST:
        k = it["key"]
        g = gold[k]
        r = rag.get(k)
        h = hol.get(k)
        er = abs(r - g) if r is not None else None
        eh = abs(h - g) if h is not None else None
        win = ""
        if er is not None and eh is not None:
            win = "HOL" if eh < er else ("RAG" if er < eh else "=")
        rs = f"{r:.1f}" if r is not None else "-"
        hs = f"{h:.1f}" if h is not None else "-"
        ers = f"{er:.1f}" if er is not None else "-"
        ehs = f"{eh:.1f}" if eh is not None else "-"
        print(f"{k:16} {it['eval_type']:7} {g:>4} {rs:>5} {hs:>5}  {ers:>7} {ehs:>7}  {win}")
        cat_g[it["category"]].append(g)
        if r is not None:
            cat_r[it["category"]].append(r)
        if h is not None:
            cat_h[it["category"]].append(h)

    print("-" * 76)
    print("[카테고리 합계]  (GOLD / RAG / HOL, 5점 만점×항목수)")
    for c in CATEGORIES:
        g = sum(cat_g[c]); r = sum(cat_r[c]); h = sum(cat_h[c])
        print(f"  {c} {CATEGORIES[c]:12} GOLD {g:>4.0f}  RAG {r:>5.1f}  HOL {h:>5.1f}")

    sr, sh = _stats(gold, rag), _stats(gold, hol)
    print("=" * 76)
    print(f"{'':16} {'MAE(낮을수록정확)':>16} {'방향일치(±1)':>14} {'편향':>8}")
    print(f"{'RAG':16} {sr['mae']:>14.2f}   {sr['within1']}/{sr['n']} ({100*sr['within1']//sr['n']}%)  {sr['bias']:>+7.2f}")
    print(f"{'Holistic':16} {sh['mae']:>14.2f}   {sh['within1']}/{sh['n']} ({100*sh['within1']//sh['n']}%)  {sh['bias']:>+7.2f}")
    better = "Holistic" if sh["mae"] < sr["mae"] else "RAG"
    print(f"→ gold 에 더 가까움: {better}  (MAE {min(sr['mae'],sh['mae']):.2f} vs {max(sr['mae'],sh['mae']):.2f})")
    print("=" * 76)


if __name__ == "__main__":
    main()
