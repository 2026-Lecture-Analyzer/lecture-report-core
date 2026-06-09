"""⑧ 리포트 로컬 러너 — scores.json + analysis.jsonl → 강의별 report_{lid}.md.

사용법:
    python -m scripts.run_report_local --scores outputs/processed/_audit_0203/scores.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.report.build import build_all  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="⑧ 리포트(scores+analysis → MD)")
    ap.add_argument("--scores", type=Path, default=config.PROCESSED_DIR / "scores.json")
    ap.add_argument("--analysis", type=Path, default=None, help="기본: <scores 폴더>/analysis.jsonl")
    ap.add_argument("--out", type=Path, default=None, help="기본: <scores 폴더>/reports/")
    ap.add_argument("--pdf", action="store_true", help="MD 외에 PDF 도 생성(reportlab+한글폰트)")
    args = ap.parse_args()
    if not args.scores.exists():
        sys.exit(f"scores 없음: {args.scores} — 먼저 ⑦ 스코어링(run_score_local) 실행")
    analysis = args.analysis or (args.scores.parent / "analysis.jsonl")
    out = args.out or (args.scores.parent / "reports")
    r = build_all(args.scores, analysis, out)
    print(f"[⑧ 리포트 MD] {r['reports']}편 → {r['out_dir']}")
    for f in r["files"]:
        print("  -", f)
    if args.pdf:
        from src.report.pdf import build_all_pdf
        rp = build_all_pdf(args.scores, analysis, out)
        if rp.get("pdfs"):
            print(f"[⑧ 리포트 PDF] {rp['pdfs']}편 (폰트 {rp['font']})")
            for f in rp["files"]:
                print("  -", f)
        else:
            print(f"[⑧ PDF] 생략 — {rp.get('skipped')}")


if __name__ == "__main__":
    main()
