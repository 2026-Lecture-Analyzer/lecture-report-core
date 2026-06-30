"""보고서 1개 렌더링 — 시계열·세션비교·세션상세·매트릭스 4탭.

원래 lecture_insights/dashboard.py 를 '특정 보고서(Report) 객체' 입력으로 일반화.
날짜·주차·강사·오전/오후는 모두 보고서 데이터에서 동적으로 도출(하드코딩 없음).
"""
from __future__ import annotations

import sys
from datetime import date as _date
from pathlib import Path
from statistics import mean

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # core/ → src import
from service import keys as keymod
from service.constants import (CAT_COLORS, CAT_NAME, CATS, ITEM_META, ITEM_ORDER,
                               SCORE_COLOR, cat_avg)
from service.store import Report
from src.report.coaching import build_coaching_report

try:
    from src.report.highlight_component import render_highlight
except Exception:  # 하이라이트 컴포넌트 없으면 카드 보기만
    render_highlight = None

WK_COLORS = ["rgba(99,102,241,0.07)", "rgba(244,114,114,0.07)", "rgba(16,185,129,0.07)",
             "rgba(245,158,11,0.07)", "rgba(14,165,233,0.07)"]


def _parse(d: str) -> _date:
    return _date.fromisoformat(d)


def _week_of(d: str, first: str) -> int:
    """첫 날짜 기준 상대 주차(7일 단위)."""
    return (_parse(d) - _parse(first)).days // 7 + 1


def _build(rpt: Report):
    """보고서 행 → 렌더링용 자료구조."""
    rows = rpt.load_score_rows()
    sess: dict = {}            # (date,session) → {item_key: score(int)}
    detail: dict = {}          # (date,session) → {item_key: full row}
    for r in rows:
        k = (r["date"], r["session"])
        detail.setdefault(k, {})[r["item_key"]] = r
        if isinstance(r.get("score"), int):
            sess.setdefault(k, {})[r["item_key"]] = r["score"]
    subj_of = {(s["date"], s["session"]): s.get("subject", "") for s in rpt.sessions}
    keys = sorted(detail.keys())
    smat = {}
    for k in keys:
        ca = cat_avg(sess.get(k, {}))
        vals = [v for v in ca.values() if v is not None]
        smat[k] = {"cat": ca, "overall": round(mean(vals), 2) if vals else None,
                   "subject": subj_of.get(k, "")}
    dates = sorted({d for d, _ in keys})
    return sess, detail, keys, dates, smat


def _report_pdf_bytes(rpt: Report):
    """리포트 → PDF bytes + 파일명. 세션 1개면 PDF, 여러 개면 ZIP. 폰트 없으면 (None,None)."""
    import io
    import tempfile
    import zipfile

    from src.report.pdf import build_lecture_pdf, register_korean_font
    from src.scoring.scoring import compute_scores

    font = register_korean_font()
    if not font:
        return None, None
    rows = rpt.load_score_rows()
    scores = compute_scores(rows)
    lids = list(scores["lectures"])
    if not lids:
        return None, None
    with tempfile.TemporaryDirectory() as td:
        paths = []
        for lid in lids:
            p = Path(td) / f"report_{lid}.pdf"
            build_lecture_pdf(lid, scores, rows, p, font)
            paths.append(p)
        if len(paths) == 1:
            return paths[0].read_bytes(), f"{rpt.name}_{lids[0]}.pdf"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for p in paths:
                z.write(p, p.name)
        return buf.getvalue(), f"{rpt.name}_리포트({len(paths)}건).zip"


def _pdf_download_ui(rpt: Report) -> None:
    """리포트 PDF 생성·다운로드 (헤더 영역). 생성 결과는 세션상태에 캐싱."""
    with st.expander("📄 리포트 PDF 저장"):
        if st.button("PDF 생성", key=f"genpdf_{rpt.report_id}"):
            with st.spinner("PDF 생성 중…"):
                data, fn = _report_pdf_bytes(rpt)
            st.session_state[f"pdf_{rpt.report_id}"] = (data, fn)
            if not data:
                st.warning("한글 폰트를 찾지 못해 PDF를 만들 수 없어요(AppleGothic/NanumGothic 필요).")
        blob = st.session_state.get(f"pdf_{rpt.report_id}")
        if blob and blob[0]:
            data, fn = blob
            mime = "application/zip" if fn.endswith(".zip") else "application/pdf"
            st.download_button("⬇️ 다운로드", data, file_name=fn, mime=mime,
                               key=f"dlpdf_{rpt.report_id}")


def render_report(rpt: Report) -> None:
    sess, detail, keys, dates, smat = _build(rpt)
    if not keys:
        st.info("아직 분석된 세션이 없습니다. **➕ 분석 추가**에서 강의 txt를 올려보세요.")
        return

    labels = rpt.session_labels          # ampm:[오전,오후] | single:[종일]
    is_ampm = rpt.mode == "ampm"
    first = dates[0]
    week_of = {d: _week_of(d, first) for d in dates}
    weeks = sorted(set(week_of.values()))
    ovs = [smat[k]["overall"] for k in keys if smat[k]["overall"] is not None]

    # ── 헤더 + 요약 지표 ──
    st.subheader(f"📊 {rpt.name}")
    cap = f"{len(keys)}세션 · {len(dates)}일"
    if rpt.meta.get("instructor"):
        cap = f"강사 {rpt.meta['instructor']} · " + cap
    st.caption(cap + f" · 모드: {'오전/오후 분리' if is_ampm else '단일 강사'}")

    _pdf_download_ui(rpt)

    cols = st.columns(4)
    cols[0].metric("전체 종합", round(mean(ovs), 2) if ovs else "—")
    if len(weeks) >= 2:
        wk_ov = {w: round(mean([smat[k]["overall"] for k in keys
                                 if week_of[k[0]] == w and smat[k]["overall"] is not None]), 2)
                 for w in weeks}
        cols[1].metric("주차 추세", wk_ov[weeks[-1]],
                       f"{wk_ov[weeks[-1]] - wk_ov[weeks[0]]:+.2f} ({weeks[0]}→{weeks[-1]}주)")
    else:
        cols[1].metric("세션 수", len(keys))
    if is_ampm:
        ampm_ov = {s: ([smat[k]["overall"] for k in keys if k[1] == s and smat[k]["overall"] is not None])
                   for s in labels}
        am = round(mean(ampm_ov["오전"]), 2) if ampm_ov["오전"] else None
        pm = round(mean(ampm_ov["오후"]), 2) if ampm_ov["오후"] else None
        cols[2].metric("오전 종합", am if am is not None else "—")
        cols[3].metric("오후 종합", pm if pm is not None else "—",
                       f"{pm - am:+.2f} vs 오전" if (am is not None and pm is not None) else None)
    else:
        cols[2].metric("기간", f"{dates[0][5:]}~{dates[-1][5:]}" if len(dates) > 1 else dates[0][5:])
        best = max(keys, key=lambda k: smat[k]["overall"] or 0)
        cols[3].metric("최고 세션", best[0][5:])

    tab_labels = ["📈  시계열 추이"] + (["🌗  오전 vs 오후"] if is_ampm else []) + \
                 ["🔍  세션 상세 (근거·원문)", "📋  세션 매트릭스",
                  "🎯  강사 코칭", "📊  수강생 피드백", "🆚  AI vs 학생"]
    tabs = st.tabs(tab_labels)
    ti = iter(tabs)

    # ══ 시계열 ══
    with next(ti):
        _tab_timeseries(keys, dates, smat, week_of, weeks)

    # ══ 오전 vs 오후 ══
    if is_ampm:
        with next(ti):
            _tab_ampm(sess, keys, smat)

    # ══ 세션 상세 ══
    with next(ti):
        _tab_detail(rpt, detail, smat, dates, labels)

    # ══ 매트릭스 ══
    with next(ti):
        _tab_matrix(keys, smat, week_of)

    # ══ 강사 코칭 ══
    with next(ti):
        _tab_coaching(rpt)

    # ══ 수강생 피드백 ══
    with next(ti):
        _tab_feedback(rpt)

    # ══ AI vs 학생 ══
    with next(ti):
        _tab_compare(rpt)


def _tab_timeseries(keys, dates, smat, week_of, weeks):
    day_cat = {d: {c: ([smat[(dd, s)]["cat"][c] for (dd, s) in keys
                        if dd == d and smat[(dd, s)]["cat"][c] is not None]) for c in CATS}
               for d in dates}
    day_cat = {d: {c: round(mean(v), 2) if v else None for c, v in cm.items()}
               for d, cm in day_cat.items()}
    xlab = [d[5:] for d in dates]
    fig = go.Figure()
    if len(weeks) >= 2:
        for i, wk in enumerate(weeks):
            idx = [j for j, d in enumerate(dates) if week_of[d] == wk]
            if idx:
                fig.add_vrect(x0=min(idx) - 0.5, x1=max(idx) + 0.5,
                              fillcolor=WK_COLORS[i % len(WK_COLORS)], line_width=0,
                              layer="below", annotation_text=f"{wk}주차", annotation_position="top")
    for c in CATS:
        fig.add_trace(go.Scatter(x=xlab, y=[day_cat[d][c] for d in dates],
                                 mode="lines+markers", name=f"{c} {CAT_NAME[c]}",
                                 line=dict(color=CAT_COLORS[c], width=2.5)))
    fig.update_layout(height=460, yaxis=dict(range=[1, 5.2], title="카테고리 평균"),
                      xaxis=dict(type="category", title="날짜"),
                      legend=dict(orientation="h", y=-0.18), margin=dict(t=30, b=10),
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    if len(weeks) >= 2:
        st.markdown("##### 주차별 종합")
        wk_rows = []
        for wk in weeks:
            wk_keys = [k for k in keys if week_of[k[0]] == wk]
            subs = sorted({str(smat[k]["subject"]).split(" — ")[0] for k in wk_keys if smat[k]["subject"]})
            row = {"주차": f"{wk}주차", "주제": ", ".join(subs)[:40]}
            for c in CATS:
                v = [smat[k]["cat"][c] for k in wk_keys if smat[k]["cat"][c] is not None]
                row[f"{c} {CAT_NAME[c]}"] = round(mean(v), 2) if v else None
            ov = [smat[k]["overall"] for k in wk_keys if smat[k]["overall"] is not None]
            row["종합"] = round(mean(ov), 2) if ov else None
            wk_rows.append(row)
        st.dataframe(pd.DataFrame(wk_rows), use_container_width=True, hide_index=True)


def _tab_ampm(sess, keys, smat):
    ampm = {s: {c: ([smat[k]["cat"][c] for k in keys if k[1] == s and smat[k]["cat"][c] is not None])
                for c in CATS} for s in ("오전", "오후")}
    ampm = {s: {c: round(mean(v), 2) if v else None for c, v in cm.items()} for s, cm in ampm.items()}
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[f"{c} {CAT_NAME[c]}" for c in CATS], y=[ampm["오전"][c] for c in CATS],
                         name="오전 세션", marker_color="#4c78a8",
                         text=[ampm["오전"][c] for c in CATS], textposition="outside"))
    fig.add_trace(go.Bar(x=[f"{c} {CAT_NAME[c]}" for c in CATS], y=[ampm["오후"][c] for c in CATS],
                         name="오후 세션", marker_color="#e45756",
                         text=[ampm["오후"][c] for c in CATS], textposition="outside"))
    fig.update_layout(height=440, barmode="group", yaxis=dict(range=[1, 5.3], title="카테고리 평균"),
                      legend=dict(orientation="h", y=-0.15), margin=dict(t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

    am_row, pm_row, diff_row = {"구분": "오전"}, {"구분": "오후"}, {"구분": "차(오전−오후)"}
    for c in CATS:
        am_row[f"{c} {CAT_NAME[c]}"] = ampm["오전"][c]
        pm_row[f"{c} {CAT_NAME[c]}"] = ampm["오후"][c]
        diff_row[f"{c} {CAT_NAME[c]}"] = (round(ampm["오전"][c] - ampm["오후"][c], 2)
                                          if ampm["오전"][c] is not None and ampm["오후"][c] is not None else None)
    st.dataframe(pd.DataFrame([am_row, pm_row, diff_row]), use_container_width=True, hide_index=True)

    st.markdown("##### 항목별 오전 vs 오후")
    items = sorted({ik for k in keys for ik in sess.get(k, {})})
    irows = []
    for ik in items:
        am = [sess[k][ik] for k in keys if k[1] == "오전" and ik in sess.get(k, {})]
        pm = [sess[k][ik] for k in keys if k[1] == "오후" and ik in sess.get(k, {})]
        if am and pm:
            name = ITEM_META.get(ik, (ik,))[0]
            irows.append({"항목": f"{name} [{ik}]", "오전": round(mean(am), 2),
                          "오후": round(mean(pm), 2), "차": round(mean(am) - mean(pm), 2)})
    if irows:
        st.dataframe(pd.DataFrame(irows).sort_values("차", ascending=False),
                     use_container_width=True, hide_index=True)


def _tab_detail(rpt, detail, smat, dates, labels):
    cda, cdb = st.columns([3, 1])
    sel_date = cda.selectbox("날짜 선택", dates, index=len(dates) - 1)
    avail = [s for s in labels if (sel_date, s) in detail]
    sel_sess = cdb.radio("세션", avail, horizontal=True) if len(avail) > 1 else (avail[0] if avail else None)
    if not sel_sess:
        st.warning("이 날짜에 분석된 세션이 없습니다.")
        return
    drow = detail.get((sel_date, sel_sess), {})
    subj = smat[(sel_date, sel_sess)]["subject"]
    ov = smat[(sel_date, sel_sess)]["overall"]
    st.markdown(f"#### {sel_date} {sel_sess} · {subj}　— 종합 **{ov}**")
    view = st.radio("보기 방식", ["🖍 원문 하이라이트", "📇 근거 카드"],
                    horizontal=True, label_visibility="collapsed")

    if view.startswith("🖍"):
        chunks_by = rpt.load_chunks()
        lec_chunks = sorted(chunks_by.get((sel_date, sel_sess), []),
                            key=lambda c: c.get("pos", c.get("chunk_id", 0)))
        items_data = [{
            "key": k, "title": ITEM_META.get(k, (k,))[0], "category": k.split("_")[0], "weight": "",
            "score": drow[k].get("score"), "verdict": drow[k].get("verdict") or "",
            "evidence": drow[k].get("evidence") or [], "eval_type": drow[k].get("eval_type") or "",
            "metric": drow[k].get("metric"),
        } for k in ITEM_ORDER if k in drow]
        if lec_chunks and render_highlight is not None:
            st.caption("좌측 항목에 마우스를 올리면(또는 클릭해 고정) 그 근거가 원문에서 형광펜으로 표시돼요.")
            render_highlight(items_data, lec_chunks, height=600)
        elif render_highlight is None:
            st.warning("하이라이트 컴포넌트를 불러오지 못해 카드 보기를 이용하세요.")
        else:
            st.warning("이 세션의 원문(chunks)을 찾지 못했습니다.")
    else:
        _evidence_cards(drow)


def _evidence_cards(drow):
    b1, b2, _ = st.columns([1.1, 1.1, 6])
    if b1.button("📂 전체 펼치기", use_container_width=True):
        st.session_state.expand_all = True
    if b2.button("📁 전체 닫기", use_container_width=True):
        st.session_state.expand_all = False
    exp_default = st.session_state.get("expand_all")
    for c in CATS:
        cat_items = [k for k in ITEM_ORDER if k.startswith(c)]
        cs = [drow[k]["score"] for k in cat_items if k in drow and isinstance(drow[k].get("score"), int)]
        cavg = round(mean(cs), 2) if cs else "—"
        expanded = exp_default if exp_default is not None else (c == "C3")
        with st.expander(f"**{c} {CAT_NAME[c]}**　·　평균 {cavg}", expanded=expanded):
            for k in cat_items:
                r = drow.get(k)
                if not r:
                    continue
                name, desc = ITEM_META.get(k, (k, ""))
                sc = r.get("score")
                color = SCORE_COLOR.get(sc, "#9ca3af")
                verdict = r.get("verdict") or ("해당없음" if sc is None else "")
                st.markdown(
                    f"<span style='background:{color};color:#fff;border-radius:6px;"
                    f"padding:2px 9px;font-weight:700'>{sc if sc is not None else 'N/A'}</span>　"
                    f"**{name}**　<span style='color:#888'>· {verdict}</span>　"
                    f"<span style='color:#aaa;font-size:0.85em'>[{k}]</span>", unsafe_allow_html=True)
                st.caption(f"📌 평가 기준: {desc}")
                if r.get("comment"):
                    st.markdown(f"**왜 이 점수?** {r['comment']}")
                ev = r.get("evidence") or []
                if ev:
                    st.markdown("**원문 근거**")
                    for e in ev:
                        st.markdown(f"> `{e.get('time', '')}` {e.get('quote', '')}")
                elif r.get("routing", {}).get("method") == "raw_metric":
                    st.markdown("*(규칙 기반 지표 — 원문 인용 대신 수치로 판정)*")
                st.divider()


def _tab_matrix(keys, smat, week_of):
    rows = []
    for k in keys:
        d, s = k
        row = {"날짜": d[5:], "주차": week_of.get(d), "세션": s,
               "주제": str(smat[k]["subject"])[:30]}
        for c in CATS:
            row[c] = smat[k]["cat"][c]
        row["종합"] = smat[k]["overall"]
        rows.append(row)
    df = pd.DataFrame(rows)
    st.dataframe(df.style.background_gradient(subset=["종합"] + CATS, cmap="RdYlGn", vmin=1, vmax=5),
                 use_container_width=True, hide_index=True, height=560)
    st.caption("색이 진한 초록=높음, 빨강=낮음.")


# ══════════════════════════════════════════════════════════════════════
# 강사 코칭 · 수강생 피드백 (CLI 기능을 보고서 탭으로)
# ══════════════════════════════════════════════════════════════════════
def _period(rows: list[dict]) -> str:
    ds = sorted({r["date"] for r in rows})
    return f"{ds[0]} ~ {ds[-1]}" if ds else ""


# 점수 배지 — 톤다운 틴트(배경, 글자). 솔리드 비비드 대신 절제된 펠릿.
_SCORE_STYLE = {1: ("#fde8e8", "#d92d20"), 2: ("#fdecd8", "#dc6803"), 3: ("#fdf3d2", "#b54708"),
                4: ("#dcf5e6", "#067647"), 5: ("#d1f0df", "#05603a")}


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _tab_coaching(rpt: Report) -> None:
    """여러 세션 종합 → 강점·개선 우선순위·LLM 코칭(카드형 UI)."""
    from src.report import coaching as co
    rows = rpt.load_score_rows()
    if not rows:
        st.info("분석된 세션이 없습니다.")
        return
    agg = co.aggregate(rows)
    if not agg:
        st.info("집계할 점수가 없습니다.")
        return
    strengths = co.pick_strengths(agg, 3)
    priorities = co.pick_priorities(agg, 3)
    overall = round(mean(it["mean"] for it in agg.values()), 2)

    c = st.columns(3)
    c[0].metric("종합 강의력", f"{overall} / 5")
    c[1].metric("대표 강점", strengths[0]["title"] if strengths else "—")
    c[2].metric("최우선 개선", priorities[0]["title"] if priorities else "—")

    # ── 강점 ──
    st.markdown('<div class="sec-h">💪 강점</div>', unsafe_allow_html=True)
    chips = "".join(f'<span class="coach-strength">{_esc(s["title"])} · {s["mean"]}/5 '
                    f'({s["trend"]:+})</span>' for s in strengths)
    st.markdown(f"<div>{chips}</div>", unsafe_allow_html=True)

    # ── 개선 우선순위 ──
    st.markdown('<div class="sec-h">🎯 개선 우선순위</div>', unsafe_allow_html=True)
    has_keys = keymod.has_keys()
    use_llm = st.checkbox("🧠 LLM 코칭 생성 (진단·개선법·예시 멘트, 과금)", value=False,
                          disabled=not has_keys, key=f"coach_llm_{rpt.report_id}")
    if not has_keys:
        st.caption("⚠️ LLM 코칭은 사이드바 키 입력 후. 키 없이도 우선순위·근거는 표시됩니다.")

    coachings: dict = {}
    if use_llm and has_keys:
        from src.refine.model import make_solar_generate_fn
        with st.spinner("코칭 생성 중 (LLM)…"):
            with keymod.applied(keymod.get_keys()):
                gen = make_solar_generate_fn()
                for p in priorities:
                    coachings[p["key"]] = co._coach_one(p, p, gen)

    for i, p in enumerate(priorities, 1):
        bg, fg = _SCORE_STYLE.get(round(p["mean"]), ("#eef0f3", "#4e5968"))
        head = (f'<div class="pri-head"><span class="num">{i}</span>'
                f'<span class="t">{_esc(p["title"])}</span>'
                f'<span class="badge" style="background:{bg};color:{fg}">{p["mean"]} / 5</span>'
                f'<span class="tagw">가중 {p["weight"]}</span>'
                f'<span class="tagw">추이 {p["trend"]:+}</span></div>')
        evi = p.get("evidence") or p.get("comments") or []
        evi = sorted(evi, key=lambda e: (e.get("score") or 9))[:3]
        evi_html = "".join(
            f'<div class="evi"><span class="tag">{_esc(e.get("date",""))} '
            f'{_esc(e.get("session",""))} · {e.get("score","")}점</span>'
            f'{_esc(e.get("quote") or e.get("comment",""))}</div>' for e in evi)
        c = coachings.get(p["key"])
        coach_html = ""
        if c:
            if c["diagnosis"]:
                coach_html += (f'<div class="coach-box"><span class="lab">진단</span><br>'
                               f'{_esc(c["diagnosis"])}</div>')
            if c["how_to"]:
                items = "".join(f"<li>{_esc(h)}</li>" for h in c["how_to"])
                coach_html += f'<div style="margin:.3rem 0"><b>개선 방법</b><ul style="margin:.2rem 0">{items}</ul></div>'
            if c["example_lines"]:
                ments = "".join(f'<span class="ment">“{_esc(m)}”</span>' for m in c["example_lines"])
                coach_html += f'<div style="margin-top:.3rem"><b>바로 쓸 수 있는 멘트</b>{ments}</div>'
        st.markdown(
            f'<div class="pri-card">{head}'
            f'<div class="pri-desc">{_esc(p.get("description",""))}</div>'
            f'<div class="evi-lab">실제 강의 근거 · 낮은 세션</div>'
            f'{evi_html}{coach_html}</div>',
            unsafe_allow_html=True)


def _ai_category_means(rows: list[dict]) -> dict:
    """AI 분석행 → 카테고리별 평균(1~5) + 전체 평균. 학생 평가와 동일 척도로 비교용."""
    by_cat: dict = {}
    allv = []
    for r in rows:
        s = r.get("score")
        if isinstance(s, (int, float)):
            by_cat.setdefault(r["category"], []).append(s)
            allv.append(s)
    out = {c: round(mean(v), 2) for c, v in by_cat.items()}
    out["overall"] = round(mean(allv), 2) if allv else None
    return out


def _ai_item_means(rows: list[dict]) -> dict:
    """AI 분석행 → 항목별 평균(1~5). 학생 항목별 평가와 비교용."""
    by: dict = {}
    for r in rows:
        s = r.get("score")
        if isinstance(s, (int, float)):
            by.setdefault(r["item_key"], []).append(s)
    return {k: round(mean(v), 2) for k, v in by.items()}


def _tab_feedback(rpt: Report) -> None:
    """공개 설문폼 관리 + 실제 수강생 응답 집계."""
    import service.feedback_forms as ff
    rows = rpt.load_score_rows()
    wid = rpt.dir.parent.parent.name      # ws_root/<wid>/reports/<rid>

    # ── 설문폼 주소 ──
    st.markdown("##### 📨 평가 설문폼")
    form = ff.load_form(rpt)
    if not form:
        st.caption("학생들에게 보낼 공개 평가 링크를 만드세요. 학생은 로그인 없이 평가만 합니다.")
        if st.button("🔗 설문폼 주소 만들기", type="primary", key=f"mkform_{rpt.report_id}"):
            ff.create_form(rpt, wid)
            st.rerun()
    else:
        url = ff.form_url(rpt)
        st.success("설문폼이 생성됐습니다 — 이 주소를 학생들에게 전달하세요:")
        st.code(url, language=None)
        c1, c2 = st.columns([1, 3])
        active = c1.toggle("폼 열림", value=form.get("active", True), key=f"act_{rpt.report_id}")
        if active != form.get("active", True):
            ff.set_active(rpt, active); st.rerun()
        c2.caption("열림=학생 제출 가능 / 닫힘=마감")

    st.divider()
    # ── 실제 응답 집계 ──
    responses = ff.load_responses(rpt)
    agg = ff.aggregate(responses)
    st.markdown(f"##### 🙋 수강생 평가 (응답 **{agg['n']}**명)")
    if agg["n"] == 0:
        st.info("아직 제출된 평가가 없습니다. 위 설문폼 주소를 학생들에게 공유하세요.")
        return
    cols = st.columns(6)
    cols[0].metric("종합 만족도", agg["overall"])
    for i, c in enumerate(ff.CAT_KEYS):
        cols[i + 1].metric(c, agg["by_cat"][c] if agg["by_cat"][c] is not None else "—")
    df = pd.DataFrame([{"카테고리": f"{c} {agg['cat_names'][c]}", "학생 평균(1~5)": agg["by_cat"][c]}
                       for c in ff.CAT_KEYS])
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("📑 항목별 학생 평가 (18항목)"):
        idf = pd.DataFrame([{"항목": ITEM_META.get(it["key"], (it["key"],))[0],
                             "학생 평균(1~5)": agg["by_item"].get(it["key"])} for it in ff.ITEMS])
        st.dataframe(idf, use_container_width=True, hide_index=True, height=460)

    comments = [r.get("comment", "").strip() for r in responses if r.get("comment", "").strip()]
    if comments:
        st.markdown(f"##### 💬 자유 의견 ({len(comments)}개)")
        if keymod.has_keys() and st.button("🧠 의견 AI 요약 (주제·감성·액션, 과금)",
                                           key=f"sumcom_{rpt.report_id}"):
            from src.feedback.summarize import summarize_comments
            from src.refine.model import make_solar_generate_fn
            with st.spinner("의견 요약 중 (LLM)…"):
                with keymod.applied(keymod.get_keys()):
                    s = summarize_comments(comments, make_solar_generate_fn())
            if s["summary"]:
                st.info(f"**전체 감성: {s['overall_sentiment'] or '—'}** — {s['summary']}")
            for t in s["themes"]:
                cnt = f" · {t['count']}회" if t["count"] else ""
                st.markdown(f"- **{t['title']}** ({t['sentiment']}{cnt}) — “{t['quote']}”")
            if s["actions"]:
                st.markdown("**개선 액션:**")
                for a in s["actions"]:
                    st.markdown(f"  - {a}")
        elif not keymod.has_keys():
            st.caption("⚠️ 의견 AI 요약은 사이드바에서 키 입력 후 가능.")
        with st.expander(f"원문 의견 {len(comments)}개 보기"):
            for cm in comments[:50]:
                st.markdown(f"- {cm}")


def _tab_compare(rpt: Report) -> None:
    """AI 평가 vs 학생 평가 차이 — 카테고리별 1~5 척도 비교."""
    import service.feedback_forms as ff
    rows = rpt.load_score_rows()
    if not rows:
        st.info("분석된 세션이 없습니다.")
        return
    agg = ff.aggregate(ff.load_responses(rpt))
    if agg["n"] == 0:
        st.info("학생 평가가 있어야 비교할 수 있습니다. **📊 수강생 피드백** 탭에서 설문폼을 공유하세요.")
        return
    ai = _ai_category_means(rows)
    st.caption(f"AI 분석(18항목 → 카테고리 평균) vs 학생 평가 {agg['n']}명 — 둘 다 1~5 척도. "
               "차이 = 학생 − AI (양수=학생이 더 후함).")

    co = st.columns(3)
    co[0].metric("AI 종합", ai.get("overall"))
    co[1].metric("학생 종합", agg["overall"])
    if ai.get("overall") is not None and agg["overall"] is not None:
        co[2].metric("차이(학생−AI)", f"{agg['overall'] - ai['overall']:+.2f}")

    rows_tbl, ai_y, st_y, cats = [], [], [], []
    for c in ff.CAT_KEYS:
        a, s = ai.get(c), agg["by_cat"][c]
        diff = round(s - a, 2) if (a is not None and s is not None) else None
        rows_tbl.append({"카테고리": f"{c} {agg['cat_names'][c]}", "AI": a, "학생": s, "차이(학생−AI)": diff})
        cats.append(c); ai_y.append(a); st_y.append(s)
    st.dataframe(pd.DataFrame(rows_tbl), use_container_width=True, hide_index=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(name="AI 평가", x=cats, y=ai_y, marker_color="#6366f1"))
    fig.add_trace(go.Bar(name="학생 평가", x=cats, y=st_y, marker_color="#f59e0b"))
    fig.update_layout(barmode="group", height=380, yaxis=dict(range=[0, 5.3], title="점수(1~5)"),
                      legend=dict(orientation="h", y=-0.2), margin=dict(t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # 인사이트: 가장 큰 괴리(카테고리)
    gaps = [(c, agg["by_cat"][c] - ai[c]) for c in ff.CAT_KEYS
            if agg["by_cat"][c] is not None and ai.get(c) is not None]
    if gaps:
        big = max(gaps, key=lambda x: abs(x[1]))
        who = "학생이 더 후하게" if big[1] > 0 else "AI가 더 후하게"
        st.info(f"카테고리 최대 괴리: **{big[0]} {agg['cat_names'][big[0]]}** (차이 {big[1]:+.2f}) — {who} 평가.")

    # ── 항목별 비교(괴리 큰 순) ──
    st.markdown("##### 항목별 비교 (괴리 큰 순)")
    ai_item = _ai_item_means(rows)
    irows = []
    for it in ff.ITEMS:
        a, s = ai_item.get(it["key"]), agg["by_item"].get(it["key"])
        diff = round(s - a, 2) if (a is not None and s is not None) else None
        irows.append({"항목": ITEM_META.get(it["key"], (it["key"],))[0],
                      "AI": a, "학생": s, "차이(학생−AI)": diff})
    irows.sort(key=lambda x: -(abs(x["차이(학생−AI)"]) if x["차이(학생−AI)"] is not None else -1))
    st.dataframe(pd.DataFrame(irows), use_container_width=True, hide_index=True, height=460)
    st.caption("AI가 박하게 본 항목(차이 양수 큼)일수록 학생 체감과 가장 벌어진 곳 — 코칭·재캘리브레이션 후보.")

    # ── 🔧 캘리브레이션 제안(학생=ground-truth, |차이|≥1.0) ──
    from src.analyze.checklist import by_key
    meta = by_key()
    sugg = []
    for it in ff.ITEMS:
        a, s = ai_item.get(it["key"]), agg["by_item"].get(it["key"])
        if a is None or s is None or abs(s - a) < 1.0:
            continue
        m = meta.get(it["key"], {})
        title, etype = m.get("title", it["key"]), m.get("eval_type", "")
        if s - a > 0:      # AI 박함 → 완화
            how = "메트릭 임계 완화" if etype == "metric" else "프롬프트(ITEM_GUIDES)에 '약한 신호도 인정' 가이드 추가"
            sugg.append((abs(s - a), f"🔼 **{title}** — AI가 {s - a:+.1f} 박함 → {how}"))
        else:              # AI 후함 → 강화
            how = "메트릭 임계 강화" if etype == "metric" else "프롬프트에 '명시적 근거 필요' 기준 강화"
            sugg.append((abs(s - a), f"🔽 **{title}** — AI가 {s - a:+.1f} 후함 → {how}"))
    sugg.sort(reverse=True)
    st.markdown("##### 🔧 캘리브레이션 제안")
    if sugg:
        st.caption("학생 평가를 기준(ground-truth)으로, AI와 |차이|≥1.0 항목의 보정 방향 (human-in-the-loop).")
        for _, line in sugg[:8]:
            st.markdown(f"- {line}")
    else:
        st.success("AI와 학생 평가가 모든 항목 ±1.0 이내 — 캘리브레이션 불필요.")
