"""⑦ 스코어링 로컬 러너 — analysis.jsonl → scores.json (규칙·LLM 없음·즉시).

사용법:
    python -m scripts.run_score_local --analysis outputs/processed/_audit_0203/analysis.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.scoring.scoring import run_scoring  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="⑦ 스코어링(analysis.jsonl → scores.json)")
    ap.add_argument("--analysis", type=Path, default=config.PROCESSED_DIR / "analysis.jsonl")
    ap.add_argument("--out", type=Path, default=None, help="기본: <analysis 폴더>/scores.json")
    args = ap.parse_args()
    if not args.analysis.exists():
        sys.exit(f"analysis 없음: {args.analysis} — 먼저 ⑥ 분석(run_analyze_local) 실행")
    out = args.out or (args.analysis.parent / "scores.json")
    sc = run_scoring(args.analysis, out)
    for lid, v in sc["lectures"].items():
        print(f"  {lid}: 종합 {v['total_score']}점 · 카테고리 {v['category_scores']}")
    print(f"요약: {sc['summary']}")


if __name__ == "__main__":
    main()
