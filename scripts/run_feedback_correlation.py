"""강의력 ↔ 수강생 피드백 상관분석 러너.

피드백 파일(--feedback jsonl)이 있으면 사용, 없으면 **합성 샘플**을 생성(세션 점수 동인 + 잡음).
세션 단위로 강의력 18항목/5카테고리와 만족도·이해도 상관(Pearson/Spearman)을 내고 리포트 md 생성.

사용법:
    # 합성 샘플 자동 생성 + 분석
    python -m scripts.run_feedback_correlation --scores ../eval/analysis_session/session_scores.jsonl
    # 실제 피드백 파일 사용(jsonl: {date,session,student_id,satisfaction,understanding,recommend})
    python -m scripts.run_feedback_correlation --scores <s> --feedback real_feedback.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.feedback import sample  # noqa: E402
from src.feedback.correlate import build_report  # noqa: E402


def _load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _infer_instructor(rows: list[dict]) -> str:
    try:
        from src.preprocess.loader import load_metadata
        meta = load_metadata()
        names = sorted({str(meta[meta["date"] == d]["instructor"].iloc[0])
                        for d in {r["date"] for r in rows} if (meta["date"] == d).any()})
        names = [n for n in names if n and n != "nan"]
        return names[0] if len(names) == 1 else (", ".join(names) or "강사")
    except Exception:
        return "강사"


def main():
    ap = argparse.ArgumentParser(description="강의력 ↔ 수강생 피드백 상관분석")
    ap.add_argument("--scores", required=True, help="분석행 jsonl(session_scores.jsonl)")
    ap.add_argument("--feedback", default=None, help="실제 피드백 jsonl(없으면 합성 샘플 생성)")
    ap.add_argument("--out", default=None, help="출력 md(기본 입력 옆 feedback_correlation.md)")
    ap.add_argument("--instructor", default=None)
    ap.add_argument("--seed", type=int, default=None, help="샘플 생성 seed")
    args = ap.parse_args()

    scores_path = Path(args.scores)
    if not scores_path.exists():
        raise SystemExit(f"분석행 파일 없음: {scores_path}")
    score_rows = _load(scores_path)
    instructor = args.instructor or _infer_instructor(score_rows)

    synthetic = args.feedback is None
    if synthetic:
        feedback = sample.generate(score_rows, seed=args.seed)
        fb_out = scores_path.parent / "sample_feedback.jsonl"
        fb_out.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in feedback),
                          encoding="utf-8")
        print(f"합성 샘플 피드백 {len(feedback)}건 생성 → {fb_out}")
    else:
        feedback = _load(Path(args.feedback))
        print(f"실제 피드백 {len(feedback)}건 로드")

    md = build_report(score_rows, feedback, instructor=instructor, synthetic=synthetic)
    out = Path(args.out) if args.out else scores_path.parent / "feedback_correlation.md"
    out.write_text(md, encoding="utf-8")
    print(f"✅ 상관분석 리포트: {out}")


if __name__ == "__main__":
    main()
