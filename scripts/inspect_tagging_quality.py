"""tagging 품질 검사 — eval_tags(키워드+임베딩 태깅)가 관련 청크를 잘 찾는지 점검.

⚠️ 이 스크립트는 embedding vector 를 재계산하지 않는다. 이미 생성된 eval_tags 를
기준으로 태깅 품질을 점검하는 사후 검수 도구다(LLM·임베딩 호출 없음).

태깅 단계(tagging.py / chunk_embed.py)가 각 청크에 eval_tags 를 단다:
    eval_tags: [{"item_key": "C4_error", "score": 0.62, "cue": "에러"}, ...]
이 스크립트는 chunks.jsonl 만으로 태깅 결과를 항목별로 집계·정렬해 사람이 검수할 수
있게 한다. 키워드 cue 로만 잡힌 저score 태그, seed_keyword 가 본문에 있는데 태그가
안 붙은 false negative 후보를 표시한다.

입력:
    chunks.jsonl    : eval_tags 보유(태깅 단계 산출)
선택:
    checklist 의 seed_keywords 로 false-negative 후보 탐지(— src import 가능 시).

사용:
    python scripts/inspect_tagging_quality.py --chunks outputs/chunks.jsonl \
        [--item C4_error] [--top 10] [--max-chars 60]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

# checklist 의 seed_keywords 를 쓸 수 있으면 false-negative 점검에 활용(없어도 동작)
try:
    from src.analyze.checklist import by_key as _checklist_by_key
    _SEEDS = {k: v.get("seed_keywords", []) for k, v in _checklist_by_key().items()}
except Exception:
    _SEEDS = {}


def load_jsonl(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _preview(text: str, n: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text[:n] + ("…" if len(text) > n else "")


def _tag_score(t: dict) -> float:
    return t.get("score", t.get("sim", 0)) or 0


def inspect(chunks_path: Path, item_filter: str | None = None,
            top: int = 10, max_chars: int = 60) -> None:
    chunks = load_jsonl(chunks_path)

    # 태깅 유무 자체 점검
    n_tagged = sum(1 for c in chunks if c.get("eval_tags"))
    print(f"전체 청크 {len(chunks)}개 중 eval_tags 보유 {n_tagged}개")
    if n_tagged == 0:
        print("※ eval_tags 가 없음. 태깅 단계(tagging.py/chunk_embed.py) 실행 여부 확인.")
        return

    # 항목별 태그 수집
    by_item: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for c in chunks:
        for t in c.get("eval_tags", []):
            by_item[t["item_key"]].append((_tag_score(t), c))

    items = [item_filter] if item_filter else sorted(by_item)
    for ik in items:
        tagged = sorted(by_item.get(ik, []), key=lambda x: -x[0])
        print("=" * 78)
        print(f"[{ik}] 태깅된 청크 {len(tagged)}개 (score 내림차순 top {top})")
        print("-" * 78)
        for score, c in tagged[:top]:
            print(f"  score={score:<6.3f} #{c['chunk_id']:<4} {_preview(c.get('clean_text',''), max_chars)}")

        # false-negative 후보: seed_keyword 가 본문에 있는데 이 항목 태그가 없는 청크
        seeds = _SEEDS.get(ik, [])
        if seeds:
            tagged_ids = {c["chunk_id"] for _, c in tagged}
            fn = []
            for c in chunks:
                if c["chunk_id"] in tagged_ids:
                    continue
                text = c.get("clean_text", "")
                if any(s in text for s in seeds):
                    fn.append(c)
            if fn:
                print(f"  ⚠ false-negative 후보({len(fn)}개): "
                      f"seed_keyword 있으나 태그 없음")
                for c in fn[:top]:
                    hit = [s for s in seeds if s in c.get("clean_text", "")]
                    print(f"    #{c['chunk_id']:<4} cue={hit} {_preview(c.get('clean_text',''), max_chars)}")

    print("=" * 78)


def main() -> None:
    ap = argparse.ArgumentParser(description="tagging/embedding 품질 검사")
    ap.add_argument("--chunks", required=True, type=Path)
    ap.add_argument("--item", default=None, help="특정 item_key 만 보기")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--max-chars", type=int, default=60)
    args = ap.parse_args()
    inspect(args.chunks, args.item, args.top, args.max_chars)


if __name__ == "__main__":
    main()
