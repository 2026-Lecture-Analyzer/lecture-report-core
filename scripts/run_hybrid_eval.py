"""⑥-하이브리드 — 스코프 인지 평가(gold 검증으로 확정된 라우팅).

gold(02-02) 결과: C2~C4 는 holistic 이 사람 수준, C1 은 raw 메트릭이 정확(holistic·RAG 둘 다
정제본에 속음). 그래서 항목별로 입력을 분기한다:

  • raw 메트릭(결정적, LLM 없음) : C1_repetition · C1_consistency · C1_completeness · C3_pace
  • holistic(전체원문 1패스 LLM)  : 나머지 14항목(C2 구조 · C3 개념 · C4 실습 · C5 상호작용)

설계 = holistic 로 18항목 채점 후, 결정적 4항목만 메트릭 점수로 **덮어쓰기**(reuse 최대).
출력은 analysis.jsonl 동일 스키마 → 같은 스코어러/리포트/대시보드 그대로.

사용법:
    python -m scripts.run_hybrid_eval --clean outputs/processed/clean.jsonl --self-consistency 3
    python -m scripts.run_hybrid_eval --dir outputs/processed/_gold_0202 --by-date --gold   # gold 대조
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.analyze.metrics import (compute_metrics, score_global_metric_item,  # noqa: E402
                                 score_metric_item)
from src.refine.model import make_solar_generate_fn  # noqa: E402
from scripts.exp_holistic_eval import _lectures, evaluate_lecture  # noqa: E402

# raw 메트릭으로 덮어쓸 결정적 항목 (나머지는 holistic 유지)
# C1·pace = 정제본이 신호 지움(§8). C5_check/engage = 구어체 cue 를 정제가 지움(§9-2).
METRIC_ITEMS = {"C1_repetition", "C3_pace", "C1_consistency", "C1_completeness",
                "C5_check", "C5_engage"}


def _metric_row(item_key: str, metrics: dict) -> dict | None:
    """item_key 의 raw 메트릭 채점 → {score, comment, metric}. 불가하면 None."""
    m = score_metric_item(item_key, metrics)
    if m["score"] is None:                       # global 지표형(C1_consistency/completeness)
        m = score_global_metric_item(item_key, metrics)
    if not m or m.get("score") is None:
        return None
    return {"score": m["score"], "comment": m["comment"], "metric": m["value"]}


def _merged_by(merged_path: Path, by_date: bool) -> dict[str, list[dict]]:
    if not merged_path.exists():
        return {}
    blocks = [json.loads(l) for l in merged_path.open(encoding="utf-8") if l.strip()]
    g: dict[str, list[dict]] = defaultdict(list)
    for b in blocks:
        lid = b["date"] if by_date else f"{b['date']}_{b['session']}"
        g[lid].append(b)
    return g


def _raw_texts_by(raw_path: Path, by_date: bool) -> dict[str, list[str]]:
    """raw.jsonl(정제 전 발화) → {lid: [발화텍스트]}. 완결성 발화단위 측정용."""
    if not raw_path.exists():
        return {}
    g: dict[str, list[str]] = defaultdict(list)
    for l in raw_path.open(encoding="utf-8"):
        if not l.strip():
            continue
        u = json.loads(l)
        lid = u["date"] if by_date else f"{u['date']}_{u['session']}"
        g[lid].append(u.get("text", ""))
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="⑥ 하이브리드 평가(raw 메트릭 + holistic)")
    ap.add_argument("--dir", type=Path, default=config.PROCESSED_DIR,
                    help="clean/merged/출력 기본 폴더")
    ap.add_argument("--clean", type=Path, default=None)
    ap.add_argument("--merged", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None, help="기본 <dir>/hybrid_analysis.jsonl")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--self-consistency", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--by-date", action="store_true", help="오전+오후 하루로 합쳐 채점")
    ap.add_argument("--gold", action="store_true", help="실행 후 gold(사람) 대조표")
    args = ap.parse_args()

    clean = args.clean or args.dir / "clean.jsonl"
    merged = args.merged or args.dir / "merged.jsonl"
    if not merged.exists():
        merged = config.PROCESSED_DIR / "merged.jsonl"      # 전체 merged 폴백
    out = args.out or args.dir / "hybrid_analysis.jsonl"
    if not clean.exists():
        sys.exit(f"clean 없음: {clean}")

    lecs = _lectures(clean, by_date=args.by_date)
    merged_g = _merged_by(merged, args.by_date)
    raw_path = args.dir / "raw.jsonl"
    if not raw_path.exists():
        raw_path = config.PROCESSED_DIR / "raw.jsonl"        # 전체 raw 폴백(완결성 발화단위)
    raw_g = _raw_texts_by(raw_path, args.by_date)

    print("─" * 60)
    print(f"백엔드 : {args.backend or config.MODEL_BACKEND} · SC {args.self_consistency} · "
          f"{'day' if args.by_date else 'session'} 단위")
    print(f"라우팅 : 메트릭(raw) {sorted(METRIC_ITEMS)} · 나머지 14항목 holistic")
    print(f"산출   : {out}")
    print("─" * 60)

    try:
        generate_fn = make_solar_generate_fn(
            backend=args.backend, max_tokens=args.max_tokens,
            temperature=config.ANALYZE_SC_TEMPERATURE if args.self_consistency > 1 else 0)
    except RuntimeError as e:
        sys.exit(f"[키 오류] {e}")

    out.parent.mkdir(parents=True, exist_ok=True)
    all_rows = []
    with out.open("w", encoding="utf-8") as w:
        for lid, secs in lecs.items():
            rows = evaluate_lecture(lid, secs, generate_fn, args.self_consistency)
            metrics = compute_metrics(merged_g.get(lid, []), raw_texts=raw_g.get(lid))
            n_over = 0
            for r in rows:
                if r["item_key"] in METRIC_ITEMS and metrics:
                    mr = _metric_row(r["item_key"], metrics)
                    if mr:
                        r.update(score=mr["score"], comment=mr["comment"],
                                 metric=mr["metric"], evidence=[], verdict="")
                        r["routing"] = {"method": "raw_metric", "negative_evidence": False}
                        r["scoring_trace"] = {"raw_scores": [mr["score"]],
                                              "final_score": mr["score"], "agreement": 1.0}
                        n_over += 1
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
            all_rows += rows
            scored = [r["score"] for r in rows if isinstance(r["score"], int)]
            print(f"  {lid}: 18항목(메트릭 덮어쓰기 {n_over}) · 평균 "
                  f"{round(sum(scored)/len(scored),2) if scored else 'NA'}")
    print(f"[하이브리드] {len(all_rows)}행 → {out}")

    if args.gold:
        from scripts.exp_gold_compare import GOLD, _stats
        from src.analyze.checklist import CHECKLIST
        pred = defaultdict(list)
        for r in all_rows:
            if isinstance(r.get("score"), int):
                pred[r["item_key"]].append(r["score"])
        pred = {k: sum(v) / len(v) for k, v in pred.items()}
        print("\n" + "=" * 60)
        print(f"GOLD({GOLD['date']}) 대조 — 하이브리드")
        print(f"{'item':16} {'GOLD':>4} {'HYB':>5} {'|Δ|':>5}")
        for it in CHECKLIST:
            g = GOLD["scores"][it["key"]]; p = pred.get(it["key"])
            d = f"{abs(p-g):.1f}" if p is not None else "-"
            print(f"{it['key']:16} {g:>4} {p if p is None else f'{p:.1f}':>5} {d:>5}")
        s = _stats(GOLD["scores"], pred)
        print("-" * 60)
        print(f"하이브리드 MAE {s['mae']:.2f} · 방향일치 {s['within1']}/{s['n']} "
              f"({100*s['within1']//s['n']}%) · 편향 {s['bias']:+.2f}")
        print("(참고 — RAG 1.47 / Holistic 1.00)")
        print("=" * 60)


if __name__ == "__main__":
    main()
