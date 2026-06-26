"""기존 30세션(김영아 15일) 데이터를 reports/kdt-김영아/ 보고서로 마이그레이션.

원본:
    eval/analysis_session/session_scores.jsonl     30세션 × 18항목 분석행
    eval/processed_session/<date>/chunks.jsonl      세션 원문 청크
    core/AI_Lecture_Analysis_Report_Generator/강의 메타데이터.csv   과목

사용: core/.venv/bin/python -m service.migrate
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from service.store import REPORTS_DIR, create_report, delete_report

CORE = Path(__file__).resolve().parents[1]
EVAL = CORE.parent / "eval"
SRC_SCORES = EVAL / "analysis_session" / "session_scores.jsonl"
SRC_CHUNKS = EVAL / "processed_session"
META_CSV = CORE / "AI_Lecture_Analysis_Report_Generator" / "강의 메타데이터.csv"

REPORT_ID = "kdt-김영아"


def _subjects() -> dict[tuple[str, str], str]:
    """(date, 오전/오후) → 과목 표시명."""
    m = {}
    with META_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sess = "오전" if row["time"].strip().startswith(("09", "9", "10", "11", "12")) else "오후"
            subj = (row.get("subject") or "").strip()
            content = (row.get("content") or "").strip()
            m[(row["date"], sess)] = f"{subj} — {content}" if content else subj
    return m


def main() -> None:
    if not SRC_SCORES.exists():
        raise SystemExit(f"원본 점수 없음: {SRC_SCORES}")

    delete_report(REPORT_ID)  # 멱등: 다시 돌리면 새로 만듦
    rpt = create_report("김영아 강사 · 백엔드 부트캠프 21기 (Java/React)",
                        instructor="김영아", mode="ampm",
                        created_at="2026-02-27T18:00:00", report_id=REPORT_ID)

    # 1) 점수행 그대로 복사
    shutil.copyfile(SRC_SCORES, rpt.scores_path)

    # 2) chunks 복사(날짜별 파일)
    rpt.chunks_dir.mkdir(exist_ok=True)
    for d in sorted(p.name for p in SRC_CHUNKS.iterdir() if p.is_dir()):
        src = SRC_CHUNKS / d / "chunks.jsonl"
        if src.exists():
            shutil.copyfile(src, rpt.chunks_path(d))

    # 3) meta.sessions 구성 — 점수행의 distinct (date,session)
    subj = _subjects()
    keys = sorted({(json.loads(l)["date"], json.loads(l)["session"])
                   for l in rpt.scores_path.open(encoding="utf-8") if l.strip()})
    rpt.meta["sessions"] = [
        {"date": d, "session": s, "subject": subj.get((d, s), ""),
         "source_file": f"{d}_kdt-backendj-21th.txt", "added_at": "2026-02-27T18:00:00"}
        for d, s in keys]
    rpt.save_meta()

    print(f"✅ 마이그레이션 완료: {rpt.dir}")
    print(f"   세션 {len(keys)}개 · 점수행 {sum(1 for _ in rpt.scores_path.open())}행 "
          f"· chunks {len(list(rpt.chunks_dir.glob('*.jsonl')))}일")
    print(f"   목록: {[r.report_id for r in __import__('service.store', fromlist=['list_reports']).list_reports()]}")


if __name__ == "__main__":
    main()
