"""⑥ 분석 엔진 로컬 러너 — chunks.jsonl → analysis.jsonl (Upstage Solar judge).

강의×18항목을 4갈래 라우팅으로 채점. 정제 러너(run_refine_local)와 같은 백엔드.
LLM 호출 = 강의당 local 9 + position 3 + global 4 = 16건(metric 2는 규칙, 호출 0).

비용 안전장치:
    --lecture LID   한 강의만 / --dry-run 계획만 / --fresh 처음부터(기본 재개)

사용법:
    python -m scripts.run_analyze_local \\
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
from src.refine.model import make_solar_generate_fn  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="⑥ 분석 엔진 로컬 러너(Upstage 기본)")
    ap.add_argument("--chunks", type=Path, default=config.PROCESSED_DIR / "chunks.jsonl")
    ap.add_argument("--merged", type=Path, default=config.PROCESSED_DIR / "merged.jsonl")
    ap.add_argument("--overview", type=Path, default=config.PROCESSED_DIR / "overview.json")
    ap.add_argument("--out", type=Path, default=None, help="기본: <chunks 폴더>/analysis.jsonl")
    ap.add_argument("--lecture", default=None, help="한 강의만(date_session)")
    ap.add_argument("--backend", default=None, help="upstage|hf (기본 config)")
    ap.add_argument("--self-consistency", type=int, default=None,
                    help="항목당 채점 반복수(>1=다수결, 비결정성·놓침 완화). 기본 config")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    samples = args.self_consistency or config.ANALYZE_SELF_CONSISTENCY

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
        # self-consistency 면 샘플 다양성 위해 temperature>0
        kw = {"temperature": config.ANALYZE_SC_TEMPERATURE} if samples > 1 else {}
        generate_fn = make_solar_generate_fn(backend=args.backend, **kw)
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
    print(f"\n✅ 완료 — {len(rows)}행 / 평균점수 {round(sum(avg)/len(avg),2) if avg else 'NA'} "
          f"/ 부정증거 {neg} / N/A {na} / 근거강등 {adj}항목")
    print("샘플:", json.dumps(rows[0], ensure_ascii=False)[:260])


if __name__ == "__main__":
    main()
