"""리포트 생성(P4) — scores.json + analysis.jsonl → 강의별 리포트.

담당: P4 (리포트·대시보드·인프라)
개발할 것: 비개발자도 이해 가능한 강의별 리포트(평가기준 핵심). v1 마크다운 → PDF/DOCX.
입력 → 출력: scores.json + analysis.jsonl → reports/report_{lecture_id}.md
참고: docs/SCHEMA.md(scores.json, analysis.jsonl), src/analyze/checklist.py(CATEGORIES, by_key)
"""
from __future__ import annotations

from pathlib import Path

from src.analyze.checklist import CATEGORIES, by_key  # noqa: F401


def build_lecture_report(lecture_id: str, scores: dict, analysis_path: Path) -> str:
    """단일 강의 마크다운 리포트 문자열 생성."""
    # TODO(P4): 종합점수 + 카테고리 점수표 + 항목별 평가(근거 인용) 마크다운 구성
    # TODO(P4): 카테고리 레이더 차트, 개선 코칭 요약 추가
    # 참고 구현: 파일 하단 주석
    raise NotImplementedError("P4: 구현 필요 — 아래 참고 구현 참조")


def build_all(scores_path: Path, analysis_path: Path, out_dir: Path) -> dict:
    """전체 강의 리포트 생성. 반환: {"reports": N, "out_dir": ...}"""
    # TODO(P4): scores.json 의 강의 전체 반복 → build_lecture_report → 파일 저장
    # TODO(P4): MD → PDF/DOCX 변환(ReportLab/python-docx/weasyprint)
    # TODO(P4): 강사별/주차별 비교 섹션
    raise NotImplementedError("P4: 구현 필요")


# ════════════════════════════════════════════════════════════════════════
# 참고 구현 (Claude 초안 — 지우고 직접 작성하세요)
# ════════════════════════════════════════════════════════════════════════
# import json
#
# def _load_jsonl(path):
#     with Path(path).open(encoding="utf-8") as f:
#         return [json.loads(line) for line in f if line.strip()]
#
# def build_lecture_report(lecture_id, scores, analysis_path):
#     lec = scores["lectures"][lecture_id]
#     rows = [r for r in _load_jsonl(analysis_path) if r["lecture_id"] == lecture_id]
#     items = by_key()
#     L = [f"# 강의 분석 리포트 — {lecture_id}\n",
#          f"- 날짜/세션: {lec['date']} {lec['session']}",
#          f"- **종합 강의력 점수: {lec['total_score']} / 100**\n",
#          "## 카테고리별 점수\n", "| 카테고리 | 점수 |", "|---|---|"]
#     for c, name in CATEGORIES.items():
#         L.append(f"| {name} | {lec['category_scores'].get(c)} |")
#     L.append("\n## 항목별 평가\n")
#     for r in rows:
#         it = items.get(r["item_key"], {})
#         L.append(f"### {CATEGORIES.get(r['category'],'')} > {it.get('title', r['item_key'])} "
#                  f"— {r.get('score')}점 ({r.get('verdict','')})")
#         if r.get("comment"):
#             L.append(f"{r['comment']}")
#         for ev in r.get("evidence", []) or []:
#             L.append(f"> \"{ev.get('quote','')}\"  (chunk {ev.get('chunk_id')})")
#         L.append("")
#     return "\n".join(L) + "\n"
#
# def build_all(scores_path, analysis_path, out_dir):
#     scores = json.loads(Path(scores_path).read_text(encoding="utf-8"))
#     out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
#     written = []
#     for lid in scores.get("lectures", {}):
#         md = build_lecture_report(lid, scores, analysis_path)
#         p = out_dir / f"report_{lid}.md"
#         p.write_text(md, encoding="utf-8")
#         written.append(str(p))
#     return {"reports": len(written), "out_dir": str(out_dir)}
