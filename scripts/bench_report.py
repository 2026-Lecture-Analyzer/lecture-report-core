"""[벤치] Upstage vs Google 결과 집계·리포트 — run_backend_bench 산출 → 비교 표.

읽음: outputs/processed/_bench/{backend}/{date}/hybrid_analysis.jsonl
산출: docs/고도화/03_백엔드_벤치_리포트.md + outputs/processed/_bench/results.json
비교: (1) gold 보유 강의는 백엔드별 MAE  (2) 전 강의는 백엔드 간 일치도(평균 |Δ|·편향·방향).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.exp_gold_compare import GOLDS, _stats  # noqa: E402
from src.analyze.checklist import CATEGORIES, CHECKLIST  # noqa: E402

BENCH = ROOT / "outputs" / "processed" / "_bench"


def _scores(path: Path) -> dict:
    if not path.exists():
        return {}
    rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    acc = defaultdict(list)
    for r in rows:
        if isinstance(r.get("score"), int):
            acc[r["item_key"]].append(r["score"])
    return {k: sum(v) / len(v) for k, v in acc.items()}


def main() -> None:
    backends = [d.name for d in BENCH.iterdir() if d.is_dir()] if BENCH.exists() else []
    if not backends:
        sys.exit(f"벤치 산출 없음: {BENCH} — 먼저 run_backend_bench")
    # {backend: {date: {item: score}}}
    data = {bk: {} for bk in backends}
    for bk in backends:
        for dd in sorted((BENCH / bk).glob("*")):
            sc = _scores(dd / "hybrid_analysis.jsonl")
            if sc:
                data[bk][dd.name] = sc

    dates = sorted(set.union(*[set(data[bk]) for bk in backends]))
    both = [d for d in dates if all(d in data[bk] for bk in backends)]
    L = ["# 백엔드 벤치 — Upstage vs Google (전체 파이프라인)", ""]
    L.append(f"- 백엔드 {backends} · 강의 {len(dates)}개(양쪽 완료 {len(both)}개)")
    L.append("- 각 강의 refine+하이브리드 채점을 백엔드별로 풀런. 점수=18항목 day 평균.\n")

    # 1) gold 대비 MAE
    gold_dates = [d for d in dates if d in GOLDS]
    L.append("## 1. 사람 채점(gold) 대비 정확도")
    if gold_dates:
        L.append("| gold 강의 | " + " | ".join(f"{bk} MAE" for bk in backends) + " |")
        L.append("|" + "---|" * (len(backends) + 1))
        agg = {bk: [] for bk in backends}
        for d in gold_dates:
            cells = []
            for bk in backends:
                if d in data[bk]:
                    s = _stats(GOLDS[d], data[bk][d])
                    agg[bk].append(s["mae"]); cells.append(f"{s['mae']:.2f}")
                else:
                    cells.append("—")
            L.append(f"| {d} | " + " | ".join(cells) + " |")
        L.append("| **평균** | " + " | ".join(
            f"**{sum(agg[bk])/len(agg[bk]):.2f}**" if agg[bk] else "—" for bk in backends) + " |")
    L.append("")

    # 2) 백엔드 간 일치도(전 강의)
    L.append("## 2. 백엔드 간 일치도 (gold 무관, 양쪽 완료 강의)")
    if both and len(backends) == 2:
        a, b = backends
        diffs, biases, within1, n = [], [], 0, 0
        per_item = defaultdict(list)
        for d in both:
            for it in CHECKLIST:
                k = it["key"]
                va, vb = data[a][d].get(k), data[b][d].get(k)
                if va is None or vb is None:
                    continue
                diffs.append(abs(va - vb)); biases.append(vb - va)
                per_item[k].append(vb - va)
                within1 += abs(va - vb) <= 1; n += 1
        if n:
            L.append(f"- 평균 |점수차| = **{sum(diffs)/len(diffs):.2f}** · "
                     f"편향({b}−{a}) = **{sum(biases)/len(biases):+.2f}** · "
                     f"±1 이내 {within1}/{n} ({100*within1//n}%)")
            # 가장 갈리는 항목 top
            rank = sorted(per_item.items(), key=lambda kv: -abs(sum(kv[1])/len(kv[1])))
            L.append(f"- 가장 갈리는 항목({b}−{a} 편향): " + ", ".join(
                f"{k} {sum(v)/len(v):+.1f}" for k, v in rank[:5]))
    L.append("")

    # 3) 카테고리 평균(전 강의)
    L.append("## 3. 카테고리별 평균 점수")
    L.append("| 카테고리 | " + " | ".join(backends) + " |")
    L.append("|" + "---|" * (len(backends) + 1))
    for c in CATEGORIES:
        keys = [it["key"] for it in CHECKLIST if it["category"] == c]
        cells = []
        for bk in backends:
            vals = [data[bk][d][k] for d in data[bk] for k in keys if k in data[bk][d]]
            cells.append(f"{sum(vals)/len(vals):.2f}" if vals else "—")
        L.append(f"| {c} {CATEGORIES[c]} | " + " | ".join(cells) + " |")
    L.append("")

    # 4) 강의별 종합(항목 평균)
    L.append("## 4. 강의별 평균 점수(18항목)")
    L.append("| 강의 | " + " | ".join(backends) + " | gold |")
    L.append("|" + "---|" * (len(backends) + 2))
    for d in dates:
        cells = []
        for bk in backends:
            sc = data[bk].get(d)
            cells.append(f"{sum(sc.values())/len(sc):.2f}" if sc else "—")
        g = GOLDS.get(d)
        gcell = f"{sum(g.values())/len(g):.2f}" if g else "—"
        L.append(f"| {d} | " + " | ".join(cells) + f" | {gcell} |")

    out = ROOT / "docs" / "고도화" / "03_백엔드_벤치_리포트.md"
    out.write_text("\n".join(L), encoding="utf-8")
    (BENCH / "results.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[리포트] → {out}")
    print("\n".join(L[:18]))


if __name__ == "__main__":
    main()
