"""③④⑤ 한방 로컬 러너 — merged.jsonl → clean.jsonl + chunks.jsonl(eval_tags).

노트북(02_refine_colab) 없이 로컬에서 정제·청킹·태깅을 끝까지 돌린다.
기본 백엔드가 Upstage API(config) 라 **GPU·모델 다운로드 불필요** — UPSTAGE_API_KEY 만 있으면 됨.

흐름: 오버랩 섹션화 → 강의별 개요 → 정제(Solar, 체크포인트/재개) → 임베딩 청킹+eval_tags 태깅 → manifest.

비용 안전장치(실제 API 호출이라 과금됨):
    --lecture LID       한 강의만(예: 2026-02-02_오전)
    --max-sections N    앞 N섹션만 정제
    --dry-run           LLM/임베딩 호출 없이 계획만 출력
    --overview-llm      개요 아웃라인을 LLM map-reduce 로(기본은 키워드만 — 호출 절약)
    --fresh             기존 clean/chunks 삭제 후 처음부터(필터 바꿀 땐 권장)

사용법:
    python -m scripts.run_refine_local --lecture 2026-02-02_오전 --max-sections 3   # 싼 동작확인
    python -m scripts.run_refine_local                                              # 전체
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.manifest import write_manifest  # noqa: E402
from src.refine.chunk_embed import run_chunk_embed  # noqa: E402
from src.refine.embedding import make_embedder_fn  # noqa: E402
from src.refine.glossary import load_glossary  # noqa: E402
from src.refine.model import make_solar_generate_fn  # noqa: E402
from src.refine.overview import build_overview  # noqa: E402
from src.refine.refine import run_refine  # noqa: E402
from src.refine.sectionize import load_merged, make_sections_with_overlap  # noqa: E402


def _lecture_id(rec: dict) -> str:
    return f"{rec['date']}_{rec['session']}"


def main() -> None:
    ap = argparse.ArgumentParser(description="③④⑤ 로컬 러너(Upstage 기본)")
    ap.add_argument("--merged", type=Path, default=config.PROCESSED_DIR / "merged.jsonl")
    ap.add_argument("--out-dir", type=Path, default=config.PROCESSED_DIR)
    ap.add_argument("--glossary", type=Path, default=config.PROCESSED_DIR / "glossary.json",
                    help="없으면 SEED_GLOSSARY 사용")
    ap.add_argument("--lecture", default=None, help="한 강의만(date_session)")
    ap.add_argument("--max-sections", type=int, default=None, help="앞 N섹션만 정제")
    ap.add_argument("--overview-llm", action="store_true", help="개요 아웃라인 LLM 생성")
    ap.add_argument("--model-backend", default=None, help="hf|upstage (기본 config)")
    ap.add_argument("--embed-backend", default=None, help="kure|upstage (기본 config)")
    ap.add_argument("--fresh", action="store_true", help="기존 산출물 삭제 후 처음부터")
    ap.add_argument("--dry-run", action="store_true", help="호출 없이 계획만")
    args = ap.parse_args()

    mb = args.model_backend or config.MODEL_BACKEND
    eb = args.embed_backend or config.EMBED_BACKEND
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_path = out_dir / "clean.jsonl"
    chunks_path = out_dir / "chunks.jsonl"

    if not args.merged.exists():
        sys.exit(f"merged.jsonl 없음: {args.merged} — 먼저 `python -m scripts.run_preprocess`")

    # ── 1) 로드 + (선택) 강의 필터 ──
    merged = load_merged(args.merged)
    if args.lecture:
        merged = [b for b in merged if _lecture_id(b) == args.lecture]
        if not merged:
            sys.exit(f"강의 {args.lecture} 에 해당하는 블록이 없음")

    # ── 2) 오버랩 섹션화 ──
    sections = make_sections_with_overlap(merged)
    if args.max_sections is not None:
        sections = sections[: args.max_sections]
    lectures = sorted({_lecture_id(b) for b in merged})

    if args.fresh:
        for p in (clean_path, chunks_path):
            p.unlink(missing_ok=True)
        print(f"[fresh] {clean_path.name}, {chunks_path.name} 삭제")

    # ── 계획 출력 ──
    print("─" * 60)
    print(f"백엔드   : 정제={mb}  임베딩={eb}"
          + (f"  (upstage 모델: {config.UPSTAGE_MODEL}/{config.UPSTAGE_EMBED_MODEL})"
             if "upstage" in (mb, eb) else ""))
    print(f"입력     : {args.merged}  ({len(merged)}블록)")
    print(f"강의     : {len(lectures)}편 {lectures[:4]}{'...' if len(lectures) > 4 else ''}")
    print(f"섹션     : {len(sections)}개  → 정제 LLM 호출 ≈ 미처리 섹션 수")
    print(f"개요     : 키워드(KoNLPy)" + (" + LLM 아웃라인" if args.overview_llm else " 만(LLM 생략)"))
    print(f"산출     : {clean_path} , {chunks_path}")
    print("─" * 60)
    if args.dry_run:
        print("[dry-run] 여기까지. 실제 호출 안 함.")
        return

    # ── 백엔드 준비(키 검증 일찍) ──
    try:
        generate_fn = make_solar_generate_fn(backend=mb)
        embed_fn = make_embedder_fn(backend=eb)
    except RuntimeError as e:
        sys.exit(f"[키 오류] {e}")

    glossary = load_glossary(args.glossary if args.glossary.exists() else None)

    # ── 3) 강의별 개요 ──
    by_lec: dict[str, list[str]] = defaultdict(list)
    for b in merged:
        by_lec[_lecture_id(b)].append(b["text"])
    ov_gen = generate_fn if args.overview_llm else None
    overviews = {lid: build_overview(txts, ov_gen) for lid, txts in by_lec.items()}
    print(f"[③ 개요] {len(overviews)}편 | 예: {lectures[0]} → "
          f"{overviews[lectures[0]]['keywords'][:5]}")

    # ── 4) 정제(체크포인트/재개) ──
    stats_refine = run_refine(sections, glossary, generate_fn, clean_path, overviews=overviews)
    print(f"[④ 정제] {stats_refine}")

    # ── 5) 임베딩 청킹 + eval_tags 태깅 ──
    stats_chunk = run_chunk_embed(clean_path, embed_fn, chunks_path)
    print(f"[⑤ 청킹+태깅] {stats_chunk}")

    # ── 커버리지 + manifest ──
    from src.refine.tagging import coverage
    chunks = [json.loads(l) for l in chunks_path.open(encoding="utf-8")]
    cov = coverage(chunks)
    zero = [k for k, v in cov.items() if v == 0]
    print(f"[커버리지] 태깅 항목 {sum(1 for v in cov.values() if v)} / "
          f"0개(부정증거 후보) {len(zero)}: {zero[:8]}")

    _model = config.UPSTAGE_MODEL if mb == "upstage" else config.MODEL_ID
    write_manifest(out_dir / "manifest_refine.json", step="refine+chunk(step3-5, local)",
                   params={"backend": mb, "embed_backend": eb, "model": _model,
                           "embed_model": (config.UPSTAGE_EMBED_MODEL if eb == "upstage"
                                           else config.EMBED_MODEL_ID),
                           "section_max_chars": config.SECTION_MAX_CHARS,
                           "tag_sim_threshold": config.TAG_SIM_THRESHOLD, "seed": config.SEED},
                   stats={"refine": stats_refine, "chunk": stats_chunk}, inputs=[args.merged])
    print(f"\n✅ 완료 — clean {stats_refine.get('new', 0)}신규 / chunks {stats_chunk['chunks']}건")
    if chunks:
        print("샘플 eval_tags:", json.dumps(chunks[0].get("eval_tags", [])[:3], ensure_ascii=False))


if __name__ == "__main__":
    main()
