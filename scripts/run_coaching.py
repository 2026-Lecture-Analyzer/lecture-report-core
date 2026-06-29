"""강사 코칭 리포트 러너 — 분석행(session_scores.jsonl) → 코칭 리포트 md.

여러 세션 분석을 집계해 강점·개선 우선순위·주차 추이를 뽑고, 우선순위 항목마다 Gemini 가
구체 코칭(진단·개선법·예시 멘트)을 단다. 강사명은 메타데이터(날짜→instructor)에서 추론.

비용 안전장치:
    --no-llm        LLM 코칭 없이 집계·우선순위만(호출 0, 빠른 미리보기).
    --priorities N  코칭할 개선 우선순위 개수(기본 3 → LLM 호출 N회).

사용법:
    python -m scripts.run_coaching --scores ../eval/analysis_session/session_scores.jsonl
    python -m scripts.run_coaching --scores <경로> --no-llm        # 호출 없이
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.report.coaching import build_coaching_report  # noqa: E402


def _load_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _infer_instructor(rows: list[dict]) -> str:
    """메타데이터(date→instructor)에서 강사명 추론. 실패 시 '강사'."""
    try:
        from src.preprocess.loader import load_metadata
        meta = load_metadata()
        dates = {r["date"] for r in rows}
        names = sorted({str(meta[meta["date"] == d]["instructor"].iloc[0])
                        for d in dates if (meta["date"] == d).any()})
        names = [n for n in names if n and n != "nan"]
        return names[0] if len(names) == 1 else (", ".join(names) or "강사")
    except Exception:
        return "강사"


def _period(rows: list[dict]) -> str:
    ds = sorted({r["date"] for r in rows})
    return f"{ds[0]} ~ {ds[-1]}" if ds else ""


def main():
    ap = argparse.ArgumentParser(description="강사 코칭 리포트 생성")
    ap.add_argument("--scores", required=True, help="분석행 jsonl 경로(session_scores.jsonl)")
    ap.add_argument("--out", default=None, help="출력 md 경로(기본 입력 옆 coaching_report.md)")
    ap.add_argument("--instructor", default=None, help="강사명(미지정 시 메타에서 추론)")
    ap.add_argument("--priorities", type=int, default=3, help="코칭할 개선 우선순위 수")
    ap.add_argument("--no-llm", action="store_true", help="LLM 코칭 없이 집계·우선순위만")
    args = ap.parse_args()

    scores_path = Path(args.scores)
    if not scores_path.exists():
        raise SystemExit(f"분석행 파일 없음: {scores_path}")
    rows = _load_rows(scores_path)
    instructor = args.instructor or _infer_instructor(rows)
    period = _period(rows)
    n_sess = len({(r["date"], r["session"]) for r in rows})
    print(f"강사: {instructor} · 기간: {period} · {n_sess}세션 · {len(rows)}행")

    gen = None
    if not args.no_llm:
        from src.refine.model import make_solar_generate_fn
        gen = make_solar_generate_fn()   # config.MODEL_BACKEND(=google) 따라감
        print(f"LLM 코칭: {config.MODEL_BACKEND} · 우선순위 {args.priorities}항목(과금)")

    md = build_coaching_report(rows, instructor=instructor, period=period,
                               generate_fn=gen, k_priority=args.priorities)

    out = Path(args.out) if args.out else scores_path.parent / "coaching_report.md"
    out.write_text(md, encoding="utf-8")
    print(f"\n✅ 코칭 리포트: {out}")


if __name__ == "__main__":
    main()
