"""context 품질 검사 — sentence block / 문맥확장이 앞뒤를 잘 가져오는지 점검.

분석 엔진(engine.py)이 local 항목 채점 시 needs_more 로 문맥을 확장한다.
이 스크립트는 analysis.jsonl 의 routing(candidate/context chunk_ids)을 읽어,
실제로 어떤 청크가 근거로 쓰였고 어떤 청크가 문맥으로 붙었는지 사람이 눈으로
검수할 수 있게 표로 덤프한다. (LLM·임베딩 호출 없음 — 순수 점검 도구)

입력:
    chunks.jsonl    : chunk_id → clean_text 조회용
    analysis.jsonl  : routing(candidate_chunk_ids, context_chunk_ids, expanded) 보유

사용:
    python scripts/inspect_context_quality.py \
        --chunks outputs/chunks.jsonl --analysis outputs/analysis.jsonl \
        [--item C4_error] [--max-chars 60]

출력: 표준출력에 항목별 (candidate | prev/next context) 미리보기.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _preview(text: str, n: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text[:n] + ("…" if len(text) > n else "")


def inspect(chunks_path: Path, analysis_path: Path,
            item_filter: str | None = None, max_chars: int = 60) -> None:
    chunks = load_jsonl(chunks_path)
    by_id = {c["chunk_id"]: c for c in chunks}
    rows = load_jsonl(analysis_path)

    shown = 0
    for r in rows:
        routing = r.get("routing", {})
        # local 류만(문맥확장 가능 항목) — candidate가 있는 행
        cand_ids = routing.get("candidate_chunk_ids", [])
        ctx_ids = routing.get("context_chunk_ids", [])
        if not cand_ids and not ctx_ids:
            continue
        if item_filter and r.get("item_key") != item_filter:
            continue

        print("=" * 78)
        print(f"[{r.get('lecture_id')}] {r.get('item_key')} "
              f"score={r.get('score')} verdict={r.get('verdict')} "
              f"expanded={routing.get('expanded')} "
              f"cross_checked={routing.get('cross_checked')}")
        print("-" * 78)

        print("  근거 후보(candidate):")
        for cid in cand_ids:
            print(f"    #{cid:<4} {_preview(by_id.get(cid, {}).get('clean_text', '(없음)'), max_chars)}")

        if ctx_ids:
            print("  확장 문맥(context):")
            for cid in sorted(ctx_ids):
                pos = "prev" if cand_ids and cid < min(cand_ids) else \
                      "next" if cand_ids and cid > max(cand_ids) else "mid"
                print(f"    #{cid:<4} [{pos}] {_preview(by_id.get(cid, {}).get('clean_text', '(없음)'), max_chars)}")

        # 인용된 evidence 가 실제 candidate/context 안에 있는지 점검
        ev_ids = [e.get("chunk_id") for e in (r.get("evidence") or [])]
        if ev_ids:
            in_scope = set(cand_ids) | set(ctx_ids)
            stray = [e for e in ev_ids if e not in in_scope]
            flag = "OK" if not stray else f"⚠ 범위밖 인용 {stray}"
            print(f"  인용 evidence={ev_ids} → {flag}")
        shown += 1

    print("=" * 78)
    print(f"점검 행 수: {shown}")
    if shown == 0:
        print("※ candidate/context chunk_ids 가 있는 행이 없음. "
              "engine.py 가 routing 로그를 남기는 버전인지 확인.")


def main() -> None:
    ap = argparse.ArgumentParser(description="context 품질 검사")
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--analysis", required=True, type=Path)
    ap.add_argument("--item", default=None, help="특정 item_key 만 보기")
    ap.add_argument("--max-chars", type=int, default=60)
    args = ap.parse_args()
    inspect(args.chunks, args.analysis, args.item, args.max_chars)


if __name__ == "__main__":
    main()
