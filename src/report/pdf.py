"""리포트 PDF 변환(⑧) — scores.json + analysis.jsonl → 강의별 report_{lid}.pdf.

reportlab + 한글 TTF(시스템 폰트 자동 탐색: macOS AppleGothic / Linux NanumGothic).
폰트를 못 찾으면 PDF 를 건너뛰고 경고만 낸다(MD 리포트는 별도 build.py).
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from src.analyze.checklist import CATEGORIES, by_key
from src.report.build import _grade, _load_jsonl, _WLABEL

# (경로, ttc 서브폰트 인덱스) — 앞에서부터 존재하는 첫 폰트 사용
_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", 0),
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
    ("/Library/Fonts/AppleGothic.ttf", 0),
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", 0),
    ("/usr/share/fonts/opentype/notosanscjk/NotoSansCJK-Regular.ttc", 1),
]


def register_korean_font(name: str = "KR") -> str | None:
    """한글 TTF 등록. 성공 시 폰트명, 실패 시 None."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if name in pdfmetrics.getRegisteredFontNames():
        return name
    for path, idx in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
                return name
            except Exception:
                continue
    return None


def _styles(font: str):
    from reportlab.lib.styles import ParagraphStyle
    return {
        "title": ParagraphStyle("t", fontName=font, fontSize=18, leading=24, spaceAfter=6),
        "meta": ParagraphStyle("m", fontName=font, fontSize=10, leading=15, textColor="#555555"),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=13, leading=18, spaceBefore=12, spaceAfter=4),
        "item": ParagraphStyle("i", fontName=font, fontSize=10.5, leading=15, spaceBefore=4),
        "body": ParagraphStyle("b", fontName=font, fontSize=9.5, leading=14, leftIndent=10, textColor="#333333"),
        "quote": ParagraphStyle("q", fontName=font, fontSize=9, leading=13, leftIndent=18,
                                textColor="#666666"),
    }


_CAT_COLORS = {
    "C1": "#6366f1", "C2": "#0ea5e9", "C3": "#10b981", "C4": "#f59e0b", "C5": "#ec4899",
}


def _kr_font_prop():
    """시스템에서 찾은 한글 TTF로 matplotlib FontProperties 반환."""
    from matplotlib.font_manager import FontProperties
    for path, _ in _FONT_CANDIDATES:
        if Path(path).exists():
            return FontProperties(fname=path)
    return FontProperties()  # fallback (글자 깨질 수 있음)


def _radar_png(category_scores: dict, width_inches: float = 4.0, height_inches: float = 3.2) -> bytes:
    """5개 카테고리 레이더 차트를 PNG bytes로 반환."""
    import io
    import math
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cats = list(CATEGORIES.keys())          # ["C1","C2","C3","C4","C5"]
    labels = [CATEGORIES[c] for c in cats]
    values = [float(category_scores.get(c) or 0) for c in cats]

    fp = _kr_font_prop()
    N = len(cats)
    angles = [2 * math.pi / N * i for i in range(N)] + [0]
    values_plot = values + [values[0]]

    fig, ax = plt.subplots(figsize=(width_inches, height_inches),
                           subplot_kw={"polar": True})
    ax.set_facecolor("#f8fafc")
    fig.patch.set_facecolor("white")

    # 그리드 원 (20 40 60 80 100)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=5.5, color="#94a3b8",
                       fontproperties=fp)
    ax.yaxis.set_tick_params(pad=1)

    # 스포크
    ax.set_xticks([2 * math.pi / N * i for i in range(N)])
    ax.set_xticklabels(labels, fontsize=6.5, color="#334155", fontproperties=fp)

    # 채우기 + 외곽선
    fill_color = "#6366f1"
    ax.fill(angles, values_plot, alpha=0.20, color=fill_color)
    ax.plot(angles, values_plot, color=fill_color, linewidth=1.6)

    # 점
    for ang, val, c in zip(angles[:-1], values, cats):
        ax.plot(ang, val, "o", color=_CAT_COLORS[c], markersize=5, zorder=5)

    ax.spines["polar"].set_color("#cbd5e1")
    ax.grid(color="#e2e8f0", linewidth=0.7)

    plt.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def build_lecture_pdf(lecture_id: str, scores: dict, analysis_rows: list[dict],
                      out_path: Path, font: str = "KR") -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    lec = scores["lectures"][lecture_id]
    items = by_key()
    rows = {r["item_key"]: r for r in analysis_rows if r["lecture_id"] == lecture_id}
    st = _styles(font)
    total = lec["total_score"]
    flow = [
        Paragraph(f"📊 강의 분석 리포트 — {escape(lecture_id)}", st["title"]),
        Paragraph(f"{lec['date']} {lec['session']} · "
                  f"<b>종합 강의력 점수 {total} / 100</b> ({_grade(total)}) · "
                  f"N/A {lec.get('n_na', 0)}", st["meta"]),
        Spacer(1, 6),
        Paragraph("카테고리별 점수", st["h2"]),
    ]
    data = [["카테고리", "점수"]] + [[CATEGORIES[c], str(lec["category_scores"].get(c))]
                                     for c in CATEGORIES]
    tbl = Table(data, colWidths=[90 * mm, 30 * mm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("ALIGN", (1, 0), (1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    # 레이더 차트
    import io
    radar_bytes = _radar_png(lec["category_scores"])
    flow.append(Image(io.BytesIO(radar_bytes), width=90 * mm, height=72 * mm))
    flow.append(Spacer(1, 4))

    flow.append(tbl)

    scored = [d for d in lec["items"] if d.get("norm") is not None]
    flow.append(Paragraph("✅ 강점 (상위 항목)", st["h2"]))
    for d in sorted(scored, key=lambda d: -d["norm"])[:3]:
        t = items.get(d["item_key"], {}).get("title", d["item_key"])
        flow.append(Paragraph(f"• <b>{escape(t)}</b> — {rows.get(d['item_key'], {}).get('score')}점",
                              st["body"]))
    flow.append(Paragraph("🔧 개선점 (하위 항목)", st["h2"]))
    for d in sorted(scored, key=lambda d: d["norm"])[:3]:
        t = items.get(d["item_key"], {}).get("title", d["item_key"])
        cm = escape((rows.get(d["item_key"], {}).get("comment") or "")[:80])
        flow.append(Paragraph(f"• <b>{escape(t)}</b> — {rows.get(d['item_key'], {}).get('score')}점: {cm}",
                              st["body"]))

    # 청크 타임스탬프 맵 (PDF 근거 인용에 사용)
    chunks_rows = _load_jsonl(out_path.parent.parent / "chunks.jsonl") if (
        out_path.parent.parent / "chunks.jsonl"
    ).exists() else []
    chunk_time_map = {
        c["chunk_id"]: f"{c.get('start_time', '')}-{c.get('end_time', '')}"
        for c in chunks_rows if c.get("start_time") and c.get("lecture_id") == lecture_id
    }

    _eval_label = {
        "metric": "[지표]", "local": "[검색]",
        "global": "[전역]", "positional": "[위치]",
    }

    flow.append(Paragraph("📋 항목별 상세 평가", st["h2"]))
    by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for it in items.values():
        by_cat[it["category"]].append(it)
    for c, name in CATEGORIES.items():
        flow.append(Paragraph(f"<b>{c} · {escape(name)}</b>", st["item"]))
        for it in by_cat[c]:
            r = rows.get(it["key"], {})
            elabel = _eval_label.get(r.get("eval_type", ""), "")
            flow.append(Paragraph(
                f"• <b>{escape(it['title'])}</b> ({_WLABEL.get(it['weight'],'')}) "
                f"{escape(elabel)} — "
                f"<b>{r.get('score')}점</b> {escape(r.get('verdict') or '')}", st["body"]))
            if r.get("metric"):
                m = r["metric"]
                mname = m.get("name", "")
                mval  = m.get("value")
                metric_parts = [f"{mname}={mval}"]
                top = m.get("top_filler")
                if top:
                    metric_parts.append(f"최다 '{top}'")
                n = m.get("n")
                if n is not None:
                    metric_parts.append(f"{n}회")
                flow.append(Paragraph(f"지표: {' · '.join(metric_parts)}", st["quote"]))
            if r.get("comment"):
                flow.append(Paragraph(escape(r["comment"]), st["quote"]))
            for ev in (r.get("evidence") or [])[:2]:
                cid = ev.get("chunk_id")
                if cid in chunk_time_map:
                    tstr = f" ({chunk_time_map[cid]})"
                elif ev.get("time"):
                    tstr = f" ({ev['time']})"
                else:
                    tstr = ""
                flow.append(Paragraph(
                    "“" + escape(ev.get("quote", "")) + "”" + escape(tstr),
                    st["quote"]))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out_path), pagesize=A4,
                      topMargin=18 * mm, bottomMargin=18 * mm,
                      leftMargin=18 * mm, rightMargin=18 * mm).build(flow)
    return str(out_path)


def build_all_pdf(scores_path: Path, analysis_path: Path, out_dir: Path) -> dict:
    import json
    font = register_korean_font()
    if not font:
        return {"pdfs": 0, "skipped": "한글 폰트를 못 찾아 PDF 생략(AppleGothic/NanumGothic 설치 필요)"}
    scores = json.loads(Path(scores_path).read_text(encoding="utf-8"))
    analysis_rows = _load_jsonl(analysis_path)
    out_dir = Path(out_dir)
    written = []
    for lid in scores.get("lectures", {}):
        p = build_lecture_pdf(lid, scores, analysis_rows, out_dir / f"report_{lid}.pdf", font)
        written.append(p)
    return {"pdfs": len(written), "out_dir": str(out_dir), "files": written, "font": font}
