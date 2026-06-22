"""리포트 생성(⑧) — scores.json + analysis.jsonl → 강의별 마크다운 리포트.

비개발자도 이해 가능하게: 종합 강의력 점수 + 카테고리 점수표 + 강점/개선점 요약 +
항목별 평가(점수·근거 인용). v1 마크다운(→ 필요 시 PDF/DOCX 변환).
"""
from __future__ import annotations

import json
from pathlib import Path

from src.analyze.checklist import CATEGORIES, by_key

_WLABEL = {"high": "높음", "mid": "중간", "low": "낮음"}


def _load_jsonl(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _grade(total: float | None) -> str:
    if total is None:
        return "—"
    return ("우수" if total >= 80 else "양호" if total >= 60
            else "보통" if total >= 40 else "개선 필요")


def build_lecture_report(lecture_id: str, scores: dict, analysis_rows: list[dict]) -> str:
    lec = scores["lectures"][lecture_id]
    items = by_key()
    rows = {r["item_key"]: r for r in analysis_rows if r["lecture_id"] == lecture_id}
    total = lec["total_score"]

    L = [f"# 📊 강의 분석 리포트 — {lecture_id}",
         "",
         f"- **날짜·세션**: {lec['date']} {lec['session']}",
         f"- **종합 강의력 점수: {total} / 100** ({_grade(total)})",
         f"- 평가 항목: 18개 · N/A {lec.get('n_na', 0)}개"
         + (" · ⚠️ 일부 항목 근거 미검색(부정 증거)" if any(d.get("negative") for d in lec["items"]) else ""),
         "",
         "## 카테고리별 점수",
         "",
         "| 카테고리 | 점수 |",
         "|---|---|"]
    for c, name in CATEGORIES.items():
        L.append(f"| {name} | {lec['category_scores'].get(c)} |")

    # 강점/개선점 — 항목 norm 기준
    scored = [d for d in lec["items"] if d.get("norm") is not None]
    top = sorted(scored, key=lambda d: -d["norm"])[:3]
    bot = sorted(scored, key=lambda d: d["norm"])[:3]
    L += ["", "## ✅ 강점 (상위 항목)", ""]
    for d in top:
        t = items.get(d["item_key"], {}).get("title", d["item_key"])
        L.append(f"- **{t}** — {rows.get(d['item_key'], {}).get('score')}점 (가중 {_WLABEL.get(items.get(d['item_key'],{}).get('weight'),'')})")
    L += ["", "## 🔧 개선점 (하위 항목)", ""]
    for d in bot:
        t = items.get(d["item_key"], {}).get("title", d["item_key"])
        cm = (rows.get(d["item_key"], {}).get("comment") or "")[:70]
        L.append(f"- **{t}** — {rows.get(d['item_key'], {}).get('score')}점: {cm}")

    # 항목별 상세(카테고리 그룹)
    L += ["", "## 📋 항목별 상세 평가", ""]
    by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for it in items.values():
        by_cat[it["category"]].append(it)
    for c, name in CATEGORIES.items():
        L.append(f"### {c} · {name}")
        for it in by_cat[c]:
            r = rows.get(it["key"], {})
            score = r.get("score")
            verdict = r.get("verdict") or ""
            L.append(f"- **{it['title']}** ({_WLABEL.get(it['weight'],'')}) — "
                     f"**{score}점** {verdict}")
            if r.get("metric"):
                L.append(f"  - 지표: {r['metric']['name']} = {r['metric']['value']}")
            if r.get("comment"):
                L.append(f"  - {r['comment']}")
            for ev in (r.get("evidence") or [])[:3]:
                L.append(f"  - > \"{ev.get('quote', '')}\" *(chunk {ev.get('chunk_id')})*")
        L.append("")

    L.append("---")
    L.append("> 본 리포트는 STT 전사 기반 자동 분석이며, 어투·전달력 등 비텍스트 요소는 "
             "반영되지 않습니다. 점수는 렉시컬 근거 기준입니다.")
    return "\n".join(L) + "\n"


def build_all(scores_path: Path, analysis_path: Path, out_dir: Path) -> dict:
    scores = json.loads(Path(scores_path).read_text(encoding="utf-8"))
    analysis_rows = _load_jsonl(analysis_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for lid in scores.get("lectures", {}):
        md = build_lecture_report(lid, scores, analysis_rows)
        p = out_dir / f"report_{lid}.md"
        p.write_text(md, encoding="utf-8")
        written.append(str(p))
    return {"reports": len(written), "out_dir": str(out_dir), "files": written}
