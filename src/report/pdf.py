"""리포트 PDF 변환(⑧) — scores.json + analysis.jsonl → 강의별 report_{lid}.pdf.

reportlab + 한글 TTF(시스템 폰트 자동 탐색: macOS AppleGothic / Linux NanumGothic).
폰트를 못 찾으면 PDF 를 건너뛰고 경고만 낸다(MD 리포트는 별도 build.py).
"""
from __future__ import annotations

import re
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
        "title": ParagraphStyle("t", fontName=font, fontSize=20, leading=24, spaceAfter=2,
                                 textColor="#0f172a"),
        "meta": ParagraphStyle("m", fontName=font, fontSize=9.5, leading=14, textColor="#64748b"),
        "score_big": ParagraphStyle("sb", fontName=font, fontSize=15, leading=22, spaceBefore=3,
                                    spaceAfter=8, textColor="#0f172a"),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=13.5, leading=18, spaceBefore=16,
                             spaceAfter=6, textColor="#1e293b"),
        "cathead": ParagraphStyle("ch", fontName=font, fontSize=11.5, leading=15, textColor="white"),
        "item": ParagraphStyle("i", fontName=font, fontSize=10.5, leading=15, spaceBefore=8),
        "comment": ParagraphStyle("c", fontName=font, fontSize=9.5, leading=14, leftIndent=12,
                                  textColor="#334155", spaceBefore=1),
        "quote": ParagraphStyle("q", fontName=font, fontSize=9, leading=13.5, leftIndent=14,
                                textColor="#64748b", spaceBefore=1),
        "body": ParagraphStyle("b", fontName=font, fontSize=10, leading=15, leftIndent=10,
                               textColor="#334155", spaceBefore=2),
        "sum_h": ParagraphStyle("sh", fontName=font, fontSize=8, leading=11, alignment=1,
                                textColor="#475569"),
        "sum_v": ParagraphStyle("sv", fontName=font, fontSize=14, leading=17, alignment=1),
        "score_c": ParagraphStyle("sc", fontName=font, fontSize=10.5, leading=14, alignment=1),
        "cat_cell": ParagraphStyle("cc", fontName=font, fontSize=10.5, leading=14, textColor="white"),
    }


_CAT_COLORS = {
    "C1": "#6366f1", "C2": "#0ea5e9", "C3": "#10b981", "C4": "#f59e0b", "C5": "#ec4899",
}


def _score_color(s) -> str:
    """1~5 점수 → 색(녹/주황/빨). 비정수면 회색."""
    if not isinstance(s, int):
        return "#64748b"
    return "#15803d" if s >= 4 else ("#b45309" if s == 3 else "#b91c1c")


def _cat_score_color(v) -> str:
    """0~100 카테고리 점수 → 색."""
    v = v or 0
    return "#15803d" if v >= 70 else ("#b45309" if v >= 50 else "#b91c1c")


# 비개발자용: 코멘트의 내부 개발 메모(괄호 속 기준·보정·단위·§표시 등) 제거
_DEV_NOTE = re.compile(r"\s*\([^)]*(?:§|기준|보정|잠정|EDA|raw|단위|대상)[^)]*\)")


def _clean_comment(s: str) -> str:
    if not s:
        return ""
    s = _DEV_NOTE.sub("", s)
    s = re.sub(r"§\S*", "", s)
    return re.sub(r"\s{2,}", " ", s).strip(" ·—-")


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
    from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    lec = scores["lectures"][lecture_id]
    items = by_key()
    rows = {r["item_key"]: r for r in analysis_rows if r["lecture_id"] == lecture_id}
    st = _styles(font)
    total = lec["total_score"]
    gcolor = _cat_score_color(total)

    # ── 헤더 ──
    flow = [
        Paragraph("강의 분석 리포트", st["title"]),
        Paragraph(f"{lec['date']} · {escape(str(lec['session']))}", st["meta"]),
        Paragraph(f"종합 강의력 <font color='{gcolor}' size='22'><b>{total}</b></font>"
                  f"<font color='#94a3b8'> / 100</font> &nbsp; "
                  f"<font color='{gcolor}'><b>{_grade(total)}</b></font>", st["score_big"]),
    ]

    # ── 맨 위 한눈 요약표 (종합 + 5개 카테고리) ──
    sum_hdr = [Paragraph("종합", st["sum_h"])] + [
        Paragraph(escape(CATEGORIES[c]), st["sum_h"]) for c in CATEGORIES]
    sum_val = [Paragraph(f"<font color='{gcolor}'><b>{total}</b></font>", st["sum_v"])] + [
        Paragraph(f"<font color='{_cat_score_color(lec['category_scores'].get(c))}'>"
                  f"<b>{lec['category_scores'].get(c)}</b></font>", st["sum_v"]) for c in CATEGORIES]
    sum_tbl = Table([sum_hdr, sum_val], colWidths=[26 * mm] * 6)
    sum_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#eef2ff")),
        ("LINEBEFORE", (1, 0), (1, -1), 1.2, colors.HexColor("#cbd5e1")),  # 종합|카테고리 구분선
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    flow.append(sum_tbl)
    flow.append(Spacer(1, 8))

    # ── 레이더 + 카테고리 막대 (나란히) ──
    import io
    radar_bytes = _radar_png(lec["category_scores"])
    cat_data = [[Paragraph("", st["meta"]),
                 Paragraph(escape(CATEGORIES[c]), st["comment"]),
                 Paragraph(f"<font color='{_cat_score_color(lec['category_scores'].get(c))}'>"
                           f"<b>{lec['category_scores'].get(c)}</b></font>", st["comment"])]
                for c in CATEGORIES]
    cat_tbl = Table(cat_data, colWidths=[5 * mm, 33 * mm, 22 * mm])
    cat_style = [("FONTNAME", (0, 0), (-1, -1), font),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                 ("LINEBELOW", (1, 0), (-1, -2), 0.4, colors.HexColor("#e2e8f0")),
                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    for i, c in enumerate(CATEGORIES):
        cat_style.append(("BACKGROUND", (0, i), (0, i), colors.HexColor(_CAT_COLORS[c])))
    cat_tbl.setStyle(TableStyle(cat_style))
    head = Table([[Image(io.BytesIO(radar_bytes), width=88 * mm, height=70 * mm), cat_tbl]],
                 colWidths=[92 * mm, 64 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    flow.append(head)

    # ── 강점 / 개선점 ──
    scored = [d for d in lec["items"] if d.get("norm") is not None]
    def _chip(score):
        return f"<font color='{_score_color(score)}'><b>{score}점</b></font>"
    flow.append(Paragraph("✅ 강점", st["h2"]))
    for d in sorted(scored, key=lambda d: -d["norm"])[:3]:
        t = items.get(d["item_key"], {}).get("title", d["item_key"])
        sc = rows.get(d["item_key"], {}).get("score")
        flow.append(Paragraph(f"• <b>{escape(t)}</b> &nbsp; {_chip(sc)}", st["body"]))
    flow.append(Paragraph("🔧 개선점", st["h2"]))
    for d in sorted(scored, key=lambda d: d["norm"])[:3]:
        t = items.get(d["item_key"], {}).get("title", d["item_key"])
        sc = rows.get(d["item_key"], {}).get("score")
        cm = escape(_clean_comment(rows.get(d["item_key"], {}).get("comment") or "")[:90])
        flow.append(Paragraph(f"• <b>{escape(t)}</b> &nbsp; {_chip(sc)}"
                              f"<br/><font color='#475569'>{cm}</font>", st["body"]))

    # ── 항목별 상세 (카테고리 컬러 헤더 + 점수칩 + 근거) ──
    _eval_human = {"metric": "정량 지표", "local": "근거 검색", "global": "전체 맥락",
                   "positional": "구간 분석"}
    flow.append(Paragraph("📋 항목별 상세 평가", st["h2"]))
    by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for it in items.values():
        by_cat[it["category"]].append(it)

    # ── 18항목 점수 요약표 (카테고리별 그룹) ──
    srows, sstyle, ri = [], [
        ("FONTNAME", (0, 0), (-1, -1), font), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, -1), 8),
    ], 0
    for c, name in CATEGORIES.items():
        srows.append([Paragraph(f"<b>{c} · {escape(name)}</b>", st["cat_cell"]), ""])
        sstyle += [("SPAN", (0, ri), (1, ri)),
                   ("BACKGROUND", (0, ri), (1, ri), colors.HexColor(_CAT_COLORS[c]))]
        ri += 1
        for it in by_cat[c]:
            r = rows.get(it["key"], {})
            srows.append([
                Paragraph(f"{escape(it['title'])} <font color='#94a3b8' size='8'>"
                          f"· {_WLABEL.get(it['weight'], '')}</font>", st["comment"]),
                Paragraph(f"<font color='{_score_color(r.get('score'))}'><b>"
                          f"{r.get('score')}점</b></font>", st["score_c"])])
            ri += 1
    sum_items = Table(srows, colWidths=[130 * mm, 26 * mm])
    sum_items.setStyle(TableStyle(sstyle))
    flow.append(sum_items)
    flow.append(Spacer(1, 12))

    for c, name in CATEGORIES.items():
        ch = Table([[Paragraph(f"<b>{c} · {escape(name)}</b>", st["cathead"])]], colWidths=[156 * mm])
        ch.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_CAT_COLORS[c])),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                ("TOPPADDING", (0, 0), (-1, -1), 5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        flow.append(Spacer(1, 8))
        flow.append(ch)
        for it in by_cat[c]:
            r = rows.get(it["key"], {})
            blk = [Paragraph(
                f"<b>{escape(it['title'])}</b> "
                f"<font color='#94a3b8' size='8'>· {_WLABEL.get(it['weight'],'')}</font> &nbsp; "
                f"{_chip(r.get('score'))} "
                f"<font color='#64748b'>{escape(r.get('verdict') or '')}</font>", st["item"])]
            cm = _clean_comment(r.get("comment") or "")
            if cm:
                blk.append(Paragraph(escape(cm), st["comment"]))
            for ev in (r.get("evidence") or [])[:2]:
                t = ev.get("time")
                tstr = f" <font color='#94a3b8' size='8'>({escape(t)})</font>" if t else ""
                blk.append(Paragraph(
                    f"<i>“{escape(ev.get('quote', ''))}”</i>{tstr}", st["quote"]))
            flow.append(KeepTogether(blk))

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
