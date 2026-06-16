"""⑥-하이브리드 — 스코프 인지 평가(gold 검증으로 확정된 라우팅).

gold(02-02) 결과: C2~C5 holistic 항목은 holistic 이 사람 수준, C1·발화속도는 raw
메트릭이 정확(holistic·RAG 둘 다 정제본에 속음). 그래서 항목별로 입력을 분기한다:

  • raw 메트릭(결정적, LLM 없음) : C1_repetition · C1_completeness · C1_consistency · C4_pace
  • holistic(전체원문 1패스 LLM)  : 나머지 14항목(C2 구조 · C3 개념 · C4_transition · C5 실습)

설계 = holistic 로 18항목 채점 후, 결정적 4항목만 메트릭 점수로 **덮어쓰기**(reuse 최대).
출력은 analysis.jsonl 동일 스키마 → 같은 스코어러/리포트/대시보드 그대로.
핵심 로직은 src/analyze/hybrid.run_hybrid_analysis 로 공통화(run_analyze_local 과 공유).

사용법:
    python -m scripts.run_hybrid_eval --clean outputs/processed/clean.jsonl --self-consistency 3
    python -m scripts.run_hybrid_eval --dir outputs/processed/_gold_0202 --by-date --gold   # gold 대조
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.analyze.hybrid import METRIC_ITEMS, run_hybrid_analysis  # noqa: E402
from src.refine.model import make_solar_generate_fn  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="⑥ 하이브리드 평가(raw 메트릭 + holistic)")
    ap.add_argument("--dir", type=Path, default=config.PROCESSED_DIR,
                    help="clean/merged/출력 기본 폴더")
    ap.add_argument("--clean", type=Path, default=None)
    ap.add_argument("--merged", type=Path, default=None)
    ap.add_argument("--raw", type=Path, default=None)
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
    raw_path = args.raw or args.dir / "raw.jsonl"
    if not raw_path.exists():
        raw_path = config.PROCESSED_DIR / "raw.jsonl"        # 전체 raw 폴백(완결성 발화단위)
    out = args.out or args.dir / "hybrid_analysis.jsonl"
    if not clean.exists():
        sys.exit(f"clean 없음: {clean}")

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

    res = run_hybrid_analysis(
        clean_path=clean, merged_path=merged, raw_path=raw_path,
        generate_fn=generate_fn, out_path=out, samples=args.self_consistency,
        by_date=args.by_date, backend=args.backend)
    all_rows = res["rows"]
    print(f"[하이브리드] {res['n_rows']}행 → {res['output']}")

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
        print("⚠ 신(新) 기준은 항목 구성이 달라졌다. 기존 gold 에 없는 신규 항목은 '(신규)'로")
        print("  표시되며, MAE 는 gold·pred 공통 항목으로만 계산된다(전체 성능 지표로 쓰지 말 것).")
        print(f"{'item':22} {'GOLD':>4} {'HYB':>5} {'|Δ|':>6}")
        for it in CHECKLIST:
            g = GOLD["scores"].get(it["key"])
            p = pred.get(it["key"])
            if g is None:                       # 신 기준에서 추가된 항목 — gold 미보유
                print(f"{it['key']:22} {'-':>4} {p if p is None else f'{p:.1f}':>5} {'(신규)':>6}")
                continue
            d = f"{abs(p-g):.1f}" if p is not None else "-"
            print(f"{it['key']:22} {g:>4} {p if p is None else f'{p:.1f}':>5} {d:>6}")
        # 공통 항목만 추려 통계(구 gold 의 삭제 항목·신 항목 불일치로 인한 오류 방지)
        common = {k for k in GOLD["scores"] if k in pred}
        gold_c = {k: GOLD["scores"][k] for k in common}
        pred_c = {k: pred[k] for k in common}
        s = _stats(gold_c, pred_c)
        print("-" * 60)
        print(f"하이브리드 MAE {s['mae']:.2f} · 방향일치 {s['within1']}/{s['n']} "
              f"({100*s['within1']//s['n'] if s['n'] else 0}%) · 편향 {s['bias']:+.2f} "
              f"(공통 {len(common)}항목 한정)")
        print("(주의 — 구 기준 RAG 1.47 / Holistic 1.00 수치와 직접 비교 불가)")
        print("=" * 60)


if __name__ == "__main__":
    main()
