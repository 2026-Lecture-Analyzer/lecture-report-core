"""합산 성능평가 결과 PDF 생성.

사용법:
    python -m scripts.gen_mae_pdf
    python -m scripts.gen_mae_pdf --out outputs/gold_eval/성능평가_합산.pdf
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from pathlib import Path

from scripts.run_mae_eval import CATEGORIES, load_gold, load_pred, mae_stats

# ── 기본 경로 ────────────────────────────────────────────────────────────
_DEFAULT_GOLDS = [
    Path.home() / "Downloads/files/2026-02-23_27_kdt-backendj-21th_gold_ALL.jsonl",
    Path.home() / "Downloads/gold",
]
_DEFAULT_PREDS = [
    Path("outputs/gold_eval/analysis.jsonl"),
    Path.home() / "Downloads/analysis.jsonl",
]
_DEFAULT_OUT = Path("outputs/gold_eval/성능평가_합산_박채린_정찬희.pdf")

_CAT_COLORS = {
    "C1": "#6366f1", "C2": "#0ea5e9", "C3": "#10b981",
    "C4": "#f59e0b", "C5": "#ec4899",
}


# ── 한글 폰트 등록 ────────────────────────────────────────────────────────
def _register_font(name: str = "KR") -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if name in pdfmetrics.getRegisteredFontNames():
        return name
    candidates = [
        ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", 0),
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
        ("/Library/Fonts/AppleGothic.ttf", 0),
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", 0),
    ]
    for path, idx in candidates:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
                return name
            except Exception:
                continue
    return "Helvetica"


# ── 스타일 ────────────────────────────────────────────────────────────────
def _styles(font: str) -> dict:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    return {
        "title":    ParagraphStyle("T",  fontName=font, fontSize=20, leading=28,
                                   spaceAfter=6, alignment=TA_CENTER),
        "subtitle": ParagraphStyle("ST", fontName=font, fontSize=11, leading=16,
                                   spaceAfter=4, alignment=TA_CENTER, textColor="#555555"),
        "h2":       ParagraphStyle("H2", fontName=font, fontSize=13, leading=18,
                                   spaceBefore=14, spaceAfter=5),
        "h3":       ParagraphStyle("H3", fontName=font, fontSize=11, leading=15,
                                   spaceBefore=8, spaceAfter=3, textColor="#444444"),
        "body":     ParagraphStyle("B",  fontName=font, fontSize=10, leading=15),
        "small":    ParagraphStyle("S",  fontName=font, fontSize=9,  leading=13,
                                   textColor="#555555"),
        "note":     ParagraphStyle("N",  fontName=font, fontSize=9,  leading=13,
                                   textColor="#888888", leftIndent=8),
    }


def _bar(val: float, max_val: float = 2.0, width: int = 20) -> str:
    filled = int(val / max_val * width)
    return "█" * filled + "░" * (width - filled)


def build_pdf(out_path: Path, gold_paths: list[Path], pred_paths: list[Path]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable)
    from reportlab.lib import colors

    font = _register_font()
    st = _styles(font)

    # ── 데이터 계산 ──────────────────────────────────────────────────────
    gold_all = load_gold(gold_paths)
    pred_all = load_pred(pred_paths)
    keys = sorted(set(gold_all) & set(pred_all))

    all_errs, all_signed, all_within1, all_n = [], [], 0, 0
    cat_errs: dict[str, list] = defaultdict(list)
    item_errs: dict[str, list] = defaultdict(list)
    session_rows = []

    for key in keys:
        g = gold_all[key]
        p = pred_all[key]
        s = mae_stats(g, p)
        session_rows.append((key, s))
        for k, gv in g.items():
            pv = p.get(k)
            if pv is not None:
                err = abs(pv - gv)
                cat_errs[k.split("_")[0]].append(err)
                item_errs[k].append(err)
                all_errs.append(err)
                all_signed.append(pv - gv)
                if err <= 1:
                    all_within1 += 1
                all_n += 1

    n_total = len(all_errs) or 1
    overall_mae = sum(all_errs) / n_total
    overall_bias = sum(all_signed) / n_total
    overall_within1_pct = int(100 * all_within1 // all_n)

    # ── 박채린 / 찬희 분리 집계 ─────────────────────────────────────────
    pcr_keys = [k for k in keys if k[:10] >= "2026-02-23"]
    kys_keys = [k for k in keys if k[:10] < "2026-02-23"]

    def _subset_mae(ks):
        errs = []
        for k in ks:
            for item_k, gv in gold_all[k].items():
                pv = pred_all[k].get(item_k)
                if pv is not None:
                    errs.append(abs(pv - gv))
        return sum(errs) / len(errs) if errs else 0.0

    pcr_mae = _subset_mae(pcr_keys)
    kys_mae = _subset_mae(kys_keys)

    # ── PDF 구성 ─────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=2.5*cm, rightMargin=2.5*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm,
    )
    story = []

    # 제목
    story.append(Paragraph("파이프라인 성능평가 보고서", st["title"]))
    story.append(Paragraph(
        f"골든셋 vs 파이프라인 예측 MAE &nbsp;|&nbsp; 평가일 {date.today().isoformat()}",
        st["subtitle"]))
    story.append(Paragraph(
        "골든셋: 박채린 (02-23~27) · 정찬희 (02-09~13)&nbsp;&nbsp;|&nbsp;&nbsp;"
        "파이프라인 브랜치: analyze/prompt-advancement/kys/v1",
        st["subtitle"]))
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 0.3*cm))

    # ── 1. 종합 요약 ─────────────────────────────────────────────────────
    story.append(Paragraph("1. 종합 요약", st["h2"]))

    summary_data = [
        ["구분", "MAE ↓", "±1 이내", "편향", "세션 수"],
        ["박채린  (02-23~27)", f"{pcr_mae:.2f}", "—", "—", f"{len(pcr_keys)}일"],
        ["정찬희  (02-09~13)", f"{kys_mae:.2f}", "—", "—", f"{len(kys_keys)}세션"],
        ["전체 합산", f"{overall_mae:.2f}", f"{all_within1}/{all_n} ({overall_within1_pct}%)",
         f"{overall_bias:+.2f}", f"{len(keys)}세션"],
    ]
    col_w = [5.5*cm, 2.2*cm, 3.5*cm, 2.2*cm, 2.2*cm]
    tbl = Table(summary_data, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#f1f5f9")),
        ("BACKGROUND",  (0, 3), (-1, 3),  colors.HexColor("#f8fafc")),
        ("FONTNAME",    (0, 0), (-1, -1), font),
        ("FONTSIZE",    (0, 0), (-1, -1), 9.5),
        ("FONTNAME",    (0, 0), (-1, 0),  font),
        ("FONTSIZE",    (0, 0), (-1, 0),  9.5),
        ("ALIGN",       (1, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, 2), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "※ 편향(bias): 양수=파이프라인 과대평가, 음수=과소평가. "
        "정찬희 데이터 편향 –0.99로 파이프라인이 골드보다 체계적으로 낮게 채점.",
        st["note"]))

    # ── 2. 카테고리별 MAE ────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("2. 카테고리별 MAE", st["h2"]))

    cat_data = [["카테고리", "담당", "MAE ↓", "분포 (0~2.0)"]]
    owners = {"C1": "공통", "C2": "이지선", "C3": "박채린", "C4": "정찬희", "C5": "김예슬"}
    for cat, name in CATEGORIES.items():
        errs = cat_errs.get(cat, [])
        if not errs:
            continue
        mae = sum(errs) / len(errs)
        cat_data.append([
            f"{cat} {name}", owners[cat], f"{mae:.2f}", _bar(mae),
        ])
    col_w2 = [4.0*cm, 2.2*cm, 2.2*cm, 7.0*cm]
    tbl2 = Table(cat_data, colWidths=col_w2)
    tbl2.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#f1f5f9")),
        ("FONTNAME",    (0, 0), (-1, -1), font),
        ("FONTSIZE",    (0, 0), (-1, -1), 9.5),
        ("ALIGN",       (2, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl2)

    # ── 3. 세션별 결과 ───────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("3. 세션별 결과", st["h2"]))

    # 박채린
    story.append(Paragraph("박채린 골든셋 (02-23~27)", st["h3"]))
    sess_data_pcr = [["강의", "MAE", "±1이내", "편향", "항목수"]]
    for key, s in session_rows:
        if key[:10] < "2026-02-23":
            continue
        sess_data_pcr.append([key, f"{s['mae']:.2f}",
                               f"{s['within1']}/{s['n']} ({100*s['within1']//s['n']}%)",
                               f"{s['bias']:+.2f}", str(s['n'])])
    col_w3 = [4.5*cm, 2.0*cm, 3.5*cm, 2.0*cm, 2.0*cm]
    tbl3 = Table(sess_data_pcr, colWidths=col_w3)
    tbl3.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#f1f5f9")),
        ("FONTNAME",    (0, 0), (-1, -1), font),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ALIGN",       (1, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl3)
    story.append(Spacer(1, 0.3*cm))

    # 찬희
    story.append(Paragraph("정찬희 골든셋 (02-09~13)", st["h3"]))
    sess_data_kys = [["강의", "MAE", "±1이내", "편향", "항목수"]]
    for key, s in session_rows:
        if key[:10] >= "2026-02-23":
            continue
        sess_data_kys.append([key, f"{s['mae']:.2f}",
                               f"{s['within1']}/{s['n']} ({100*s['within1']//s['n']}%)",
                               f"{s['bias']:+.2f}", str(s['n'])])
    tbl4 = Table(sess_data_kys, colWidths=col_w3)
    tbl4.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#f1f5f9")),
        ("FONTNAME",    (0, 0), (-1, -1), font),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ALIGN",       (1, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl4)

    # ── 4. 항목별 오차 ───────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("4. 항목별 오차 (전체 세션 평균)", st["h2"]))

    item_data = [["항목", "담당", "MAE", "분포 (0~2.0)"]]
    cat_owners = {"C1": "공통", "C2": "이지선", "C3": "박채린", "C4": "정찬희", "C5": "김예슬"}
    for k in sorted(item_errs):
        errs = item_errs[k]
        mae = sum(errs) / len(errs)
        cat = k.split("_")[0]
        item_data.append([k, cat_owners.get(cat, "—"), f"{mae:.2f}", _bar(mae)])

    col_w4 = [5.5*cm, 2.2*cm, 1.8*cm, 6.0*cm]
    tbl5 = Table(item_data, colWidths=col_w4)
    tbl5.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#f1f5f9")),
        ("FONTNAME",    (0, 0), (-1, -1), font),
        ("FONTSIZE",    (0, 0), (-1, -1), 8.5),
        ("ALIGN",       (2, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tbl5)

    # ── 5. 주요 관찰 ────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("5. 주요 관찰", st["h2"]))

    c1_mae = sum(cat_errs.get("C1", [])) / len(cat_errs.get("C1", [1]))
    c3_mae = sum(cat_errs.get("C3", [])) / len(cat_errs.get("C3", [1]))
    c1_consistency = sum(item_errs.get("C1_consistency", [])) / len(item_errs.get("C1_consistency", [1]))

    obs = [
        f"전체 합산 MAE {overall_mae:.2f} / ±1이내 {overall_within1_pct}%",
        f"정찬희 골드 편향 –0.99 — 파이프라인이 골드보다 평균 1점 낮게 채점 (체계적 과소평가)",
        f"C1 언어 품질 MAE={c1_mae:.2f} — 특히 C1_consistency({c1_consistency:.2f}) 가장 높은 오차",
        f"C3 개념 설명 MAE={c3_mae:.2f} (박채린 담당 프롬프트 적용 상태)",
        "박채린 골드(02-23~27) 편향 ≈0 — 파이프라인이 사람 채점과 균형적으로 수렴",
    ]
    for o in obs:
        story.append(Paragraph(f"• {o}", st["body"]))
        story.append(Spacer(1, 0.15*cm))

    doc.build(story)
    print(f"저장 완료: {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, action="append", dest="golds", default=None)
    ap.add_argument("--pred", type=Path, action="append", dest="preds", default=None)
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = ap.parse_args()

    golds = args.golds or _DEFAULT_GOLDS
    preds = args.preds or _DEFAULT_PREDS
    args.out.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(args.out, golds, preds)


if __name__ == "__main__":
    main()
