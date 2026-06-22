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
from service.constants import (CAT_COLORS, CAT_NAME, CATS, ITEM_META, ITEM_ORDER,
                               SCORE_COLOR, cat_avg)
from service.store import Report

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
                 ["🔍  세션 상세 (근거·원문)", "📋  세션 매트릭스"]
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
