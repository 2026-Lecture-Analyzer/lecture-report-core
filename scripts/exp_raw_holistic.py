"""[실험] raw-holistic — 정제 전 원문(merged.text) 전체를 holistic 에 먹여 채점.

가설: holistic 이 C1·C5 에서 약했던 건 clean_text(필러·반말·cue 삭제)를 읽어서다.
raw 를 읽으면 결함·상호작용 cue 를 직접 보므로 메트릭 없이도 맞출 수 있다.
단, C1_consistency(존댓말 비율)는 LLM 이 정량화를 못 해 메트릭이 더 정확(Exp2) →
--metric-consistency 로 그 항목만 raw 메트릭으로 덮어쓰는 변형도 지원.

출력 analysis.jsonl 동일 스키마. day 단위(기본) — gold(하루 전체)와 정합.

사용법:
    python -m scripts.exp_raw_holistic --merged outputs/processed/merged.jsonl --date 2026-02-02 --gold --self-consistency 3
    python -m scripts.exp_raw_holistic --merged outputs/processed/merged.jsonl --all --self-consistency 3   # 전 강의 변별력
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.analyze.metrics import compute_metrics, score_global_metric_item  # noqa: E402
from src.refine.model import make_solar_generate_fn  # noqa: E402
from scripts.exp_holistic_eval import evaluate_lecture  # noqa: E402


def _raw_sections(blocks: list[dict]) -> list[dict]:
    """merged 블록 → holistic 입력 섹션(raw text). 시간순."""
    return [{"date": b["date"], "session": b["session"], "file": b.get("file"),
             "section_id": b["block_id"], "start_time": b["start_time"],
             "clean_text": b["text"]}
            for b in sorted(blocks, key=lambda x: (x.get("start_sec", 0), x["block_id"]))]


def main() -> None:
    ap = argparse.ArgumentParser(description="[실험] raw-holistic 평가")
    ap.add_argument("--merged", type=Path, default=config.PROCESSED_DIR / "merged.jsonl")
    ap.add_argument("--date", default=None, help="한 날짜만(예: 2026-02-02)")
    ap.add_argument("--all", action="store_true", help="전 강의(day 단위) — 변별력 측정")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--backend", default=None)
    ap.add_argument("--self-consistency", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--metric-consistency", action="store_true",
                    help="C1_consistency 만 raw honorific 메트릭으로 덮어쓰기(Exp2 권장)")
    ap.add_argument("--gold", action="store_true")
    args = ap.parse_args()

    blocks = [json.loads(l) for l in args.merged.open(encoding="utf-8") if l.strip()]
    byday: dict[str, list[dict]] = defaultdict(list)
    for b in blocks:
        byday[b["date"]].append(b)
    if args.date:
        byday = {args.date: byday.get(args.date, [])}
    elif not args.all:
        sys.exit("--date 또는 --all 필요")
    byday = {d: v for d, v in byday.items() if v}

    out = args.out or config.PROCESSED_DIR / "raw_holistic_analysis.jsonl"
    print("─" * 60)
    print(f"raw-holistic · {args.backend or config.MODEL_BACKEND} · SC {args.self_consistency} · "
          f"{len(byday)}강의 · metric-consistency={args.metric_consistency}")
    print("─" * 60)
    try:
        gen = make_solar_generate_fn(
            backend=args.backend, max_tokens=args.max_tokens,
            temperature=config.ANALYZE_SC_TEMPERATURE if args.self_consistency > 1 else 0)
    except RuntimeError as e:
        sys.exit(f"[키 오류] {e}")

    out.parent.mkdir(parents=True, exist_ok=True)
    all_rows = []
    with out.open("w", encoding="utf-8") as w:
        for d in sorted(byday):
            secs = _raw_sections(byday[d])
            rows = evaluate_lecture(d, secs, gen, args.self_consistency)
            if args.metric_consistency:
                m = compute_metrics(byday[d])
                mc = score_global_metric_item("C1_consistency", m)
                if mc:
                    for r in rows:
                        if r["item_key"] == "C1_consistency":
                            r.update(score=mc["score"], comment=mc["comment"],
                                     metric=mc["value"], evidence=[], verdict="")
                            r["routing"] = {"method": "raw_metric"}
            for r in rows:
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
            all_rows += rows
            scored = [r["score"] for r in rows if isinstance(r["score"], int)]
            print(f"  {d}: 평균 {sum(scored)/len(scored):.2f}")
    print(f"[raw-holistic] {len(all_rows)}행 → {out}")

    if args.gold:
        from scripts.exp_gold_compare import GOLD, _stats
        from src.analyze.checklist import CHECKLIST
        pred = defaultdict(list)
        for r in all_rows:
            if r["lecture_id"] == GOLD["date"] and isinstance(r.get("score"), int):
                pred[r["item_key"]].append(r["score"])
        pred = {k: sum(v) / len(v) for k, v in pred.items()}
        if pred:
            print("\n" + "=" * 56)
            print(f"GOLD({GOLD['date']}) 대조 — raw-holistic")
            print(f"{'item':16} {'GOLD':>4} {'RAW':>5} {'|Δ|':>4}")
            for it in CHECKLIST:
                g = GOLD["scores"][it["key"]]; p = pred.get(it["key"])
                print(f"{it['key']:16} {g:>4} {p if p is None else f'{p:.1f}':>5} "
                      f"{'' if p is None else f'{abs(p-g):.1f}':>4}")
            s = _stats(GOLD["scores"], pred)
            print(f"raw-holistic MAE {s['mae']:.2f} · 방향일치 {s['within1']}/{s['n']} "
                  f"({100*s['within1']//s['n']}%) · 편향 {s['bias']:+.2f}")
            print("(참고 — RAG 1.47 / clean-Holistic 1.00 / Hybrid 0.61)")
            print("=" * 56)

    if args.all and len(all_rows) > 18:      # 변별력(전 강의 항목별 분산)
        from collections import Counter
        from src.analyze.checklist import CHECKLIST
        byk = defaultdict(list)
        for r in all_rows:
            if isinstance(r.get("score"), int):
                byk[r["item_key"]].append(r["score"])
        print("\n[변별력] 항목별 점수 고유값(상수면 무의미)")
        for it in CHECKLIST:
            vals = byk.get(it["key"], [])
            print(f"  {it['key']:16} 분포 {dict(sorted(Counter(vals).items()))}")


if __name__ == "__main__":
    main()
