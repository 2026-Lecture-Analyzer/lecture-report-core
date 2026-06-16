"""⑥ 분석 엔진 로컬 러너 — 기본 Hybrid, --legacy 로 기존 RAG 경로 보존.

기본(Hybrid): clean/merged/raw → analysis.jsonl. holistic 14항목 + raw 메트릭 4항목.
    LLM 호출 = 강의당 holistic 1패스 × self-consistency 회(메트릭 4항목은 규칙, 호출 0).

--legacy(기존 RAG): chunks.jsonl → analysis.jsonl (Upstage Solar judge).
    강의×18항목을 4갈래 라우팅으로 채점.
    LLM 호출 = 강의당 local 9 + position 3 + global 4 = 16건(metric 2는 규칙, 호출 0).

비용 안전장치:
    --lecture LID   한 강의만 / --dry-run 계획만 / --fresh 처음부터(legacy 기본 재개)

사용법:
    # 기본 Hybrid
    python -m scripts.run_analyze_local --fresh
    # 단일 강의
    python -m scripts.run_analyze_local --lecture 2026-02-02_오전 --fresh
    # 기존 RAG
    python -m scripts.run_analyze_local --legacy \\
        --chunks outputs/processed/_audit_0203/chunks.jsonl --lecture 2026-02-03_오전
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.analyze.engine import load_jsonl, run_analysis  # noqa: E402
from src.analyze.hybrid import run_hybrid_analysis  # noqa: E402
from src.refine.model import make_solar_generate_fn  # noqa: E402


def _make_generate_fn(backend, samples, max_tokens):
    # self-consistency 면 샘플 다양성 위해 temperature>0
    kw = {"temperature": config.ANALYZE_SC_TEMPERATURE} if samples > 1 else {}
    # ⚠ holistic 은 한 호출로 18항목 JSON 배열을 통째로 출력 → max_tokens 부족 시 꼬리 항목이
    #   잘려 파싱 실패(None). 기본 1024 로는 부족하므로 반드시 넉넉히 넘긴다(§exp_holistic_eval).
    return make_solar_generate_fn(backend=backend, max_tokens=max_tokens, **kw)


def _run_hybrid(args, samples: int) -> None:
    """기본 경로 — clean/merged/raw 기반 하이브리드 평가."""
    clean = args.clean
    merged = args.merged
    raw_path = args.raw
    if not clean.exists():
        sys.exit(f"clean 없음: {clean} — 먼저 정제(run_refine_local) 실행")
    out_path = args.out or (clean.parent / "analysis.jsonl")

    # 강의 수 파악(dry-run·로그용) — holistic 코어 지연 import
    from scripts.exp_holistic_eval import _lectures
    lecs = _lectures(clean, by_date=args.by_date)
    if args.lecture:
        lecs = {k: v for k, v in lecs.items() if k == args.lecture}
        if not lecs:
            sys.exit(f"강의 {args.lecture} 없음(clean): {clean}")
    lectures = sorted(lecs)

    print("─" * 60)
    print(f"방식   : Hybrid (holistic 14항목 + raw 메트릭 4항목)")
    print(f"백엔드 : 분석={args.backend or config.MODEL_BACKEND}"
          + (f" ({config.UPSTAGE_MODEL})" if (args.backend or config.MODEL_BACKEND) == "upstage" else ""))
    print(f"입력   : clean={clean} · merged={merged} · raw={raw_path}")
    print(f"강의   : {len(lectures)}편 {lectures} · {'day' if args.by_date else 'session'} 단위")
    print(f"LLM 호출: 강의당 holistic 1패스 × SC {samples}회 (메트릭 4항목은 규칙, 호출 0)")
    print(f"산출   : {out_path}")
    print("─" * 60)
    if args.dry_run:
        print("[dry-run] 여기까지.")
        return

    try:
        generate_fn = _make_generate_fn(args.backend, samples, args.max_tokens)
    except RuntimeError as e:
        sys.exit(f"[키 오류] {e}")

    res = run_hybrid_analysis(
        clean_path=clean, merged_path=merged, raw_path=raw_path,
        generate_fn=generate_fn, out_path=out_path, samples=samples,
        by_date=args.by_date, backend=args.backend,
        only_lecture=args.lecture)

    rows = load_jsonl(out_path)
    avg = [r["score"] for r in rows if r.get("score") is not None]
    na = sum(1 for r in rows if r.get("score") is None)
    print(f"\n✅ 완료(Hybrid) — {res['n_rows']}행 / 평균점수 "
          f"{round(sum(avg)/len(avg),2) if avg else 'NA'} / 메트릭 덮어쓰기 "
          f"{res['n_overwritten']} / N/A {na}")
    if rows:
        print("샘플:", json.dumps(rows[0], ensure_ascii=False)[:260])


def _run_legacy(args, samples: int) -> None:
    """--legacy 경로 — 기존 RAG/태깅 기반 분석 엔진(engine.run_analysis)."""
    if not args.chunks.exists():
        sys.exit(f"chunks 없음: {args.chunks} — 먼저 정제·태깅(run_refine_local) 실행")
    out_path = args.out or (args.chunks.parent / "analysis.jsonl")

    chunks = load_jsonl(args.chunks)
    if args.lecture:
        chunks = [c for c in chunks if f"{c['date']}_{c['session']}" == args.lecture]
        if not chunks:
            sys.exit(f"강의 {args.lecture} 청크 없음")
    lectures = sorted({f"{c['date']}_{c['session']}" for c in chunks})
    n_local = sum(1 for c in chunks for t in c.get("eval_tags", []))  # 참고용

    # 태그 0개 → 교차검증 1건씩 추가됨. 강의×태깅대상항목 중 태그 0개인 수를 추정.
    from src.analyze.checklist import taggable_items
    tag_keys = [it["key"] for it in taggable_items()]
    n_crosscheck = 0
    for lid in lectures:
        lec_chunks = [c for c in chunks if f"{c['date']}_{c['session']}" == lid]
        tagged_keys = {t["item_key"] for c in lec_chunks for t in c.get("eval_tags", [])}
        n_crosscheck += sum(1 for k in tag_keys if k not in tagged_keys)

    base_calls = 16 * len(lectures) * samples
    cross_calls = n_crosscheck * samples
    print("─" * 60)
    print(f"방식   : Legacy RAG (engine.run_analysis)")
    print(f"백엔드 : 분석={args.backend or config.MODEL_BACKEND}"
          + (f" ({config.UPSTAGE_MODEL})" if (args.backend or config.MODEL_BACKEND) == "upstage" else ""))
    print(f"입력   : {args.chunks} ({len(chunks)}청크, 태그 {n_local}개)")
    print(f"강의   : {len(lectures)}편 {lectures}")
    print(f"LLM 호출: 강의당 ~16건×{samples}회(SC) = {base_calls}건"
          + (f" + 태그0 교차검증 ~{cross_calls}건 → 총 ~{base_calls + cross_calls}건"
             if n_crosscheck else f" → 총 ~{base_calls}건")
          + (f" · self-consistency {samples}회 다수결" if samples > 1 else ""))
    print(f"산출   : {out_path}")
    print("─" * 60)
    if args.dry_run:
        print("[dry-run] 여기까지.")
        return

    if args.fresh:
        Path(out_path).unlink(missing_ok=True)

    try:
        generate_fn = _make_generate_fn(args.backend, samples, args.max_tokens)
    except RuntimeError as e:
        sys.exit(f"[키 오류] {e}")

    # --lecture 필터 시 임시 chunks 파일로 좁혀 실행
    chunks_path = args.chunks
    if args.lecture:
        tmp = Path(tempfile.mkdtemp()) / "chunks.jsonl"
        tmp.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")
        chunks_path = tmp

    stats = run_analysis(chunks_path, generate_fn, out_path,
                         merged_path=args.merged, overview_path=args.overview, samples=samples)
    print(f"[⑥ 분석] {stats}")

    rows = load_jsonl(out_path)
    avg = [r["score"] for r in rows if r.get("score") is not None]
    neg = sum(1 for r in rows if r.get("routing", {}).get("negative_evidence"))
    na = sum(1 for r in rows if r.get("score") is None)
    adj = sum(1 for r in rows if r.get("scoring_trace", {}).get("evidence_adjusted"))
    print(f"\n✅ 완료(Legacy RAG) — {len(rows)}행 / 평균점수 "
          f"{round(sum(avg)/len(avg),2) if avg else 'NA'} / 부정증거 {neg} / N/A {na} / 근거강등 {adj}항목")
    if rows:
        print("샘플:", json.dumps(rows[0], ensure_ascii=False)[:260])


def main() -> None:
    ap = argparse.ArgumentParser(description="⑥ 분석 엔진 로컬 러너(기본 Hybrid · --legacy RAG)")
    # 공통
    ap.add_argument("--out", type=Path, default=None,
                    help="기본: <입력 폴더>/analysis.jsonl")
    ap.add_argument("--lecture", default=None, help="한 강의만(date_session)")
    ap.add_argument("--backend", default=None, help="upstage|hf (기본 config)")
    ap.add_argument("--self-consistency", type=int, default=None,
                    help="항목당 채점 반복수(>1=다수결, 비결정성·놓침 완화). 기본 config")
    ap.add_argument("--max-tokens", type=int, default=8000,
                    help="LLM 출력 토큰 상한. Hybrid holistic 은 18항목을 한 번에 출력하므로 "
                         "넉넉히(기본 8000). 1024 면 꼬리 항목이 잘려 파싱 실패한다.")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    # Hybrid(기본) 입력
    ap.add_argument("--clean", type=Path, default=config.PROCESSED_DIR / "clean.jsonl")
    ap.add_argument("--raw", type=Path, default=config.PROCESSED_DIR / "raw.jsonl")
    ap.add_argument("--by-date", action="store_true",
                    help="오전/오후 세션을 하루 단위로 합쳐 평가")
    # Legacy RAG 입력
    ap.add_argument("--legacy", action="store_true",
                    help="기존 RAG/태깅 기반 분석 엔진(engine.run_analysis) 사용")
    ap.add_argument("--chunks", type=Path, default=config.PROCESSED_DIR / "chunks.jsonl",
                    help="(legacy) 태깅된 chunks.jsonl")
    ap.add_argument("--overview", type=Path, default=config.PROCESSED_DIR / "overview.json",
                    help="(legacy/global) overview.json")
    # merged 는 양쪽 공통(지표 계산)
    ap.add_argument("--merged", type=Path, default=config.PROCESSED_DIR / "merged.jsonl")
    args = ap.parse_args()

    samples = args.self_consistency or config.ANALYZE_SELF_CONSISTENCY

    if args.legacy:
        _run_legacy(args, samples)
    else:
        _run_hybrid(args, samples)


if __name__ == "__main__":
    main()