"""대시보드(P4) — Streamlit 강의력 분석 대시보드.

실행: .venv/bin/streamlit run src/report/dashboard.py
"""
from __future__ import annotations

import base64
import html
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import config
from src.analyze.checklist import CATEGORIES, by_category, by_key
from src.report.build import _grade, _load_jsonl

# ── 페이지 설정 ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="강의력 분석 대시보드",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    section[data-testid="stSidebar"] > div { padding-top: 1.5rem; }

    div[data-testid="metric-container"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px 20px;
    }
</style>
""", unsafe_allow_html=True)

# ── 상수 ─────────────────────────────────────────────────────────────────
_WEIGHT_LABEL = {"high": "높음", "mid": "중간", "low": "낮음"}
_CAT_COLORS = {
    "C1": "#6366f1", "C2": "#0ea5e9",
    "C3": "#10b981", "C4": "#f59e0b", "C5": "#ec4899",
}
_SCORE_COLOR = {
    5: "#059669", 4: "#34d399",
    3: "#f59e0b", 2: "#f97316", 1: "#ef4444",
}


def _item_color(score: int | None) -> str:
    return _SCORE_COLOR.get(score, "#94a3b8")  # type: ignore[arg-type]


def _cat_color(v: float | None) -> str:
    if v is None:
        return "#94a3b8"
    return "#059669" if v >= 70 else "#f59e0b" if v >= 50 else "#ef4444"


# ── 차트 ─────────────────────────────────────────────────────────────────
def _radar_fig(cat_keys: list[str], cat_values: list[float]) -> go.Figure:
    labels = [CATEGORIES[c] for c in cat_keys]
    fig = go.Figure(go.Scatterpolar(
        r=cat_values + [cat_values[0]],
        theta=labels + [labels[0]],
        fill="toself",
        fillcolor="rgba(99,102,241,0.15)",
        line=dict(color="#6366f1", width=2),
        marker=dict(size=6, color="#6366f1"),
        hovertemplate="%{theta}: <b>%{r}점</b><extra></extra>",
    ))
    fig.update_layout(
        polar=dict(
            bgcolor="#f8fafc",
            angularaxis=dict(tickfont=dict(size=12, color="#374151")),
            radialaxis=dict(
                visible=True, range=[0, 100],
                tickvals=[20, 40, 60, 80, 100],
                tickfont=dict(size=9, color="#94a3b8"),
                gridcolor="#e2e8f0",
            ),
        ),
        showlegend=False,
        margin=dict(t=20, b=20, l=40, r=40),
        height=320,
        paper_bgcolor="white",
    )
    return fig


def _bar_fig(cat_keys: list[str], cat_values: list[float]) -> go.Figure:
    labels = [CATEGORIES[c] for c in cat_keys]
    colors = [_CAT_COLORS[c] for c in cat_keys]
    fig = go.Figure(go.Bar(
        x=labels, y=cat_values,
        marker_color=colors,
        text=[f"{v}점" for v in cat_values],
        textposition="outside",
        textfont=dict(size=12, color="#374151"),
        hovertemplate="%{x}: <b>%{y}점</b><extra></extra>",
    ))
    fig.update_layout(
        yaxis=dict(range=[0, 115], tickfont=dict(color="#94a3b8"), gridcolor="#f1f5f9"),
        xaxis=dict(tickfont=dict(size=11, color="#374151")),
        margin=dict(t=30, b=10, l=10, r=10),
        height=320,
        paper_bgcolor="white", plot_bgcolor="white",
        bargap=0.35,
    )
    return fig


def _total_trend_fig(by_date: dict[str, float]) -> go.Figure:
    dates, values = zip(*sorted(by_date.items()))
    fig = go.Figure(go.Scatter(
        x=list(dates), y=list(values),
        mode="lines+markers+text",
        line=dict(color="#6366f1", width=2.5),
        marker=dict(size=8, color="#6366f1"),
        text=[f"{v}점" for v in values],
        textposition="top center",
        textfont=dict(size=11),
        hovertemplate="%{x}: <b>%{y}점</b><extra></extra>",
    ))
    fig.update_layout(
        yaxis=dict(range=[0, 105], title="점수", gridcolor="#f1f5f9",
                   tickfont=dict(color="#94a3b8")),
        xaxis=dict(tickfont=dict(size=11, color="#374151")),
        margin=dict(t=10, b=10, l=10, r=10),
        height=280, paper_bgcolor="white", plot_bgcolor="white",
    )
    return fig


def _cat_trend_fig(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for cat_name, color in zip(df.columns, _CAT_COLORS.values()):
        fig.add_trace(go.Scatter(
            x=df.index, y=df[cat_name],
            mode="lines+markers", name=cat_name,
            line=dict(color=color, width=2),
            marker=dict(size=7, color=color),
            hovertemplate=f"{cat_name}<br>%{{x}}: <b>%{{y}}점</b><extra></extra>",
        ))
    fig.update_layout(
        yaxis=dict(range=[0, 105], title="점수", gridcolor="#f1f5f9",
                   tickfont=dict(color="#94a3b8")),
        xaxis=dict(tickfont=dict(size=11, color="#374151")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=11)),
        margin=dict(t=40, b=10, l=10, r=10),
        height=320, paper_bgcolor="white", plot_bgcolor="white",
    )
    return fig


# ── 원문 하이라이트 HTML 컴포넌트 ─────────────────────────────────────────
def _highlight_component(
    items_data: list[dict],
    chunks: list[dict],
    height: int = 600,
) -> None:
    """항목 리스트(좌, 카테고리 그룹) + 원문 형광펜 하이라이트(우) 인터랙티브 뷰.

    hover: 근거 하이라이트 + 자동스크롤
    click: 고정(pin) — 다시 클릭하면 해제
    """
    chunk_map = {c["chunk_id"]: html.escape(c["clean_text"]) for c in chunks}
    chunk_ids_ordered = [c["chunk_id"] for c in chunks]

    # 카테고리별 그룹핑
    by_cat: dict[str, list[dict]] = {c: [] for c in sorted(CATEGORIES)}
    for item in items_data:
        by_cat[item["category"]].append(item)

    items_html_parts: list[str] = []
    for cat_key in sorted(CATEGORIES):
        items_in_cat = by_cat.get(cat_key, [])
        if not items_in_cat:
            continue
        cat_name = CATEGORIES[cat_key]
        dot_color = _CAT_COLORS.get(cat_key, "#94a3b8")

        # 카테고리 헤더
        items_html_parts.append(f"""
        <div class="cat-header">
          <span class="cat-dot" style="background:{dot_color}"></span>
          <span>{cat_key} · {cat_name}</span>
        </div>""")

        for item in items_in_cat:
            score = item.get("score")
            color = _item_color(score)
            weight = _WEIGHT_LABEL.get(item.get("weight", ""), "")
            verdict = html.escape((item.get("verdict") or "")[:100])
            title = html.escape(item.get("title", ""))
            cat = item.get("category", "")
            evidence = item.get("evidence", [])
            quotes_json = json.dumps([e.get("quote", "") for e in evidence], ensure_ascii=False)
            chunk_ids_json = json.dumps([e.get("chunk_id", -1) for e in evidence])
            score_disp = str(score) if score is not None else "N/A"

            items_html_parts.append(f"""
        <div class="item-row"
             data-quotes='{html.escape(quotes_json, quote=True)}'
             data-chunk-ids='{chunk_ids_json}'
             onmouseenter="onHover(this)"
             onmouseleave="onLeave(this)"
             onclick="onClick(this)">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <span class="item-title">{title}</span>
            <span class="item-score" style="color:{color}">{score_disp}점</span>
          </div>
          <div style="display:flex;align-items:center;gap:5px;margin-top:2px">
            <span class="item-weight">{weight}</span>
            {f'<span class="item-verdict">{verdict}</span>' if verdict else ''}
          </div>
        </div>""")

    items_html = "\n".join(items_html_parts)

    # 원문 청크 HTML
    chunks_html_parts: list[str] = []
    for cid in chunk_ids_ordered:
        text = chunk_map.get(cid, "")
        chunks_html_parts.append(
            f'<p class="chunk" id="chunk-{cid}" data-cid="{cid}"'
            f' data-orig="{html.escape(text, quote=True)}">{text}</p>'
        )
    chunks_html = "\n".join(chunks_html_parts)
    chunk_map_json = json.dumps(chunk_map, ensure_ascii=False)

    raw_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #1e293b;
    background: white;
  }}

  .container {{
    display: flex;
    height: {height}px;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    overflow: hidden;
  }}

  /* ── 좌측 항목 패널 ── */
  .items-panel {{
    width: 36%;
    min-width: 220px;
    overflow-y: auto;
    background: #f8fafc;
    border-right: 1px solid #e2e8f0;
    padding: 10px 8px;
    flex-shrink: 0;
  }}
  .panel-label {{
    font-size: 11px;
    font-weight: 600;
    color: #94a3b8;
    letter-spacing: .05em;
    text-transform: uppercase;
    padding: 0 4px 8px;
    border-bottom: 1px solid #e2e8f0;
    margin-bottom: 6px;
  }}

  /* 카테고리 헤더 */
  .cat-header {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10.5px;
    font-weight: 700;
    color: #64748b;
    letter-spacing: .04em;
    text-transform: uppercase;
    padding: 10px 8px 4px;
    margin-top: 2px;
  }}
  .cat-dot {{
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }}

  .item-row {{
    padding: 8px 10px;
    border-radius: 8px;
    margin-bottom: 3px;
    cursor: pointer;
    border: 1px solid transparent;
    transition: background .12s, border-color .12s, box-shadow .12s;
    user-select: none;
  }}
  .item-row:hover, .item-row.active {{
    background: white;
    border-color: #c7d2fe;
    box-shadow: 0 1px 6px rgba(99,102,241,.12);
  }}
  .item-row.pinned {{
    background: #eff6ff;
    border-color: #6366f1;
    box-shadow: 0 1px 8px rgba(99,102,241,.22);
  }}
  .item-title {{
    font-size: 12.5px;
    font-weight: 600;
    color: #1e293b;
    flex: 1;
    margin-right: 6px;
  }}
  .item-weight {{
    font-size: 10px;
    color: #94a3b8;
    background: #e2e8f0;
    border-radius: 4px;
    padding: 1px 5px;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .item-score {{
    font-size: 13px;
    font-weight: 700;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .item-verdict {{
    font-size: 11px;
    color: #64748b;
    line-height: 1.4;
  }}

  /* ── 우측 원문 패널 ── */
  .text-panel {{
    flex: 1;
    overflow-y: auto;
    padding: 14px 20px;
    background: white;
  }}
  .text-header {{
    font-size: 11px;
    font-weight: 600;
    color: #94a3b8;
    letter-spacing: .05em;
    text-transform: uppercase;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 8px;
    margin-bottom: 14px;
  }}

  .chunk {{
    font-size: 13.5px;
    line-height: 1.85;
    color: #374151;
    margin-bottom: 18px;
    padding-bottom: 18px;
    border-bottom: 1px solid #f8fafc;
    transition: opacity .2s;
  }}
  .chunk.dimmed {{ opacity: .2; }}
  .chunk.active  {{ opacity: 1; }}

  mark.hl {{
    background: #fef08a;
    border-radius: 3px;
    padding: 1px 1px;
    box-decoration-break: clone;
    -webkit-box-decoration-break: clone;
  }}

  ::-webkit-scrollbar {{ width: 5px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: #e2e8f0; border-radius: 4px; }}
</style>
</head>
<body>
<div class="container">

  <!-- 좌: 항목 리스트 -->
  <div class="items-panel">
    <div class="panel-label">평가 항목 &nbsp;· hover / click 고정</div>
    {items_html}
  </div>

  <!-- 우: 원문 -->
  <div class="text-panel">
    <div class="text-header" id="text-header">강의 원문</div>
    <div id="text-content">
      {chunks_html}
    </div>
  </div>

</div>

<script>
const chunkMap = {chunk_map_json};
let currentRow = null;
let pinnedRow  = null;
let leaveTimer = null;

function escRe(s) {{
  return s.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
}}

function applyHighlights(text, quotes) {{
  let out = text;
  quotes.forEach(q => {{
    if (!q || q.length < 4) return;
    try {{
      const re = new RegExp('(' + escRe(q) + ')', 'g');
      out = out.replace(re, '<mark class="hl">$1</mark>');
    }} catch(e) {{}}
  }});
  return out;
}}

function resetChunks() {{
  document.querySelectorAll('.chunk').forEach(el => {{
    const cid = parseInt(el.dataset.cid);
    el.innerHTML = chunkMap[cid] ?? el.dataset.orig ?? '';
    el.classList.remove('dimmed', 'active');
  }});
  document.getElementById('text-header').textContent = '강의 원문';
}}

function applyRowHighlight(row) {{
  const quotes   = JSON.parse(row.dataset.quotes   || '[]');
  const chunkIds = JSON.parse(row.dataset.chunkIds || '[]');
  const relevant = new Set(chunkIds);

  resetChunks();
  if (quotes.length === 0) return;

  let scrolled = false;
  document.querySelectorAll('.chunk').forEach(el => {{
    const cid = parseInt(el.dataset.cid);
    if (!relevant.has(cid)) {{
      el.classList.add('dimmed');
    }} else {{
      el.classList.add('active');
      el.innerHTML = applyHighlights(chunkMap[cid] ?? '', quotes);
      if (!scrolled) {{
        el.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
        scrolled = true;
      }}
    }}
  }});

  document.getElementById('text-header').innerHTML =
    '근거 청크 ' + chunkIds.join(', ') + ' &nbsp;·&nbsp; 인용 ' + quotes.length + '건';
}}

function onHover(row) {{
  if (pinnedRow && pinnedRow !== row) return;
  clearTimeout(leaveTimer);
  if (currentRow && currentRow !== row) currentRow.classList.remove('active');
  currentRow = row;
  row.classList.add('active');
  applyRowHighlight(row);
}}

function onLeave(row) {{
  if (pinnedRow === row) return;
  leaveTimer = setTimeout(() => {{
    if (currentRow === row) {{
      row.classList.remove('active');
      currentRow = null;
      resetChunks();
    }}
  }}, 400);
}}

function onClick(row) {{
  if (pinnedRow === row) {{
    pinnedRow = null;
    row.classList.remove('pinned');
  }} else {{
    if (pinnedRow) pinnedRow.classList.remove('pinned');
    pinnedRow = row;
    row.classList.add('pinned');
    clearTimeout(leaveTimer);
    if (currentRow && currentRow !== row) currentRow.classList.remove('active');
    currentRow = row;
    row.classList.add('active');
    applyRowHighlight(row);
  }}
}}
</script>
</body>
</html>"""

    encoded = base64.b64encode(raw_html.encode("utf-8")).decode("ascii")
    st.iframe(src=f"data:text/html;base64,{encoded}", height=height + 4)


# ── 데이터 로드 ───────────────────────────────────────────────────────────
@st.cache_data
def load_data(
    scores_path: str, analysis_path: str, chunks_path: str
) -> tuple[dict, list[dict], list[dict]]:
    scores = json.loads(Path(scores_path).read_text(encoding="utf-8"))
    analysis = _load_jsonl(Path(analysis_path))
    chunks: list[dict] = []
    if Path(chunks_path).exists():
        chunks = _load_jsonl(Path(chunks_path))
    return scores, analysis, chunks


@st.cache_data
def _get_pdf_bytes(lecture_id: str, scores_path: str, analysis_path: str) -> bytes | None:
    from src.report.pdf import build_lecture_pdf, register_korean_font
    font = register_korean_font()
    if not font:
        return None
    scores_d = json.loads(Path(scores_path).read_text(encoding="utf-8"))
    analysis_d = _load_jsonl(Path(analysis_path))
    tmp = tempfile.mktemp(suffix=".pdf")
    try:
        build_lecture_pdf(lecture_id, scores_d, analysis_d, Path(tmp), font)
        return Path(tmp).read_bytes()
    except Exception:
        return None
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🎓 강의력 분석")
    st.divider()

    default_scores   = str(config.PROCESSED_DIR / "scores.json")
    default_analysis = str(config.PROCESSED_DIR / "analysis.jsonl")
    default_chunks   = str(config.PROCESSED_DIR / "chunks.jsonl")

    scores_input   = st.text_input("scores.json 경로",   default_scores)
    analysis_input = st.text_input("analysis.jsonl 경로", default_analysis)
    chunks_input   = st.text_input("chunks.jsonl 경로",   default_chunks)

    sp, ap, cp = Path(scores_input), Path(analysis_input), Path(chunks_input)
    if not sp.exists():
        st.error("scores.json 파일을 찾을 수 없습니다.")
        st.stop()
    if not ap.exists():
        st.error("analysis.jsonl 파일을 찾을 수 없습니다.")
        st.stop()

    scores, analysis_rows, all_chunks = load_data(str(sp), str(ap), str(cp))
    lectures = sorted(scores.get("lectures", {}))
    if not lectures:
        st.error("분석된 강의가 없습니다.")
        st.stop()

    st.markdown("### 강의 선택")
    selected = st.selectbox(" ", lectures, label_visibility="collapsed")

    st.divider()
    summary = scores.get("summary", {})
    ca, cb = st.columns(2)
    ca.metric("전체 강의", f"{summary.get('n_lectures', len(lectures))}편")
    avg = summary.get("avg_total")
    if avg is not None:
        cb.metric("전체 평균", f"{avg:.1f}점")

    st.divider()
    pdf_bytes = _get_pdf_bytes(selected, str(sp), str(ap))
    if pdf_bytes:
        st.download_button(
            label="📄 PDF 다운로드",
            data=pdf_bytes,
            file_name=f"report_{selected}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    else:
        st.caption("한글 폰트 미설치로 PDF 생성 불가")


# ── 데이터 준비 ───────────────────────────────────────────────────────────
lec = scores["lectures"][selected]
items_meta = by_key()
rows_by_key = {r["item_key"]: r for r in analysis_rows if r["lecture_id"] == selected}

cat_keys   = sorted(lec["category_scores"])
cat_values = [lec["category_scores"][c] for c in cat_keys]
total      = lec["total_score"]
scored_items = [d for d in lec["items"] if d.get("norm") is not None]
neg_count    = sum(1 for d in lec["items"] if d.get("negative"))

lec_chunks = [c for c in all_chunks if c.get("lecture_id") == selected]


# ── 페이지 헤더 ───────────────────────────────────────────────────────────
st.markdown("## 📊 강의 분석 리포트")
st.caption(f"{lec.get('date', '')} · {lec.get('session', '')}세션 · {selected}")
st.divider()

tab_ov, tab_items, tab_trend = st.tabs(["📈  개요", "📋  항목별 상세 + 원문", "📅  추이 분석"])


# ════════════════════════════════════════════════════════
# TAB 1 · 개요
# ════════════════════════════════════════════════════════
with tab_ov:
    m1, m2, m3, m4 = st.columns(4)
    best_cat  = max(lec["category_scores"], key=lambda k: lec["category_scores"][k])
    worst_cat = min(lec["category_scores"], key=lambda k: lec["category_scores"][k])

    m1.metric("종합 강의력 점수", f"{total} / 100",
              delta=_grade(total), delta_color="off")
    m2.metric("최고 카테고리", CATEGORIES[best_cat],
              delta=f"{lec['category_scores'][best_cat]}점", delta_color="off")
    m3.metric("최저 카테고리", CATEGORIES[worst_cat],
              delta=f"{lec['category_scores'][worst_cat]}점", delta_color="off")
    m4.metric("부정 증거", f"{neg_count}항목",
              delta="근거 미검색", delta_color="off")

    st.markdown("")

    c_r, c_b = st.columns(2)
    with c_r:
        st.markdown("##### 카테고리별 점수")
        st.plotly_chart(_radar_fig(cat_keys, cat_values),
                        width="stretch", config={"displayModeBar": False})
    with c_b:
        st.markdown("##### 카테고리 비교")
        st.plotly_chart(_bar_fig(cat_keys, cat_values),
                        width="stretch", config={"displayModeBar": False})

    st.divider()

    top3 = sorted(scored_items, key=lambda d: -d["norm"])[:3]
    bot3 = sorted(scored_items, key=lambda d:  d["norm"])[:3]
    cs, cw = st.columns(2)

    with cs:
        st.markdown("##### ✅ 강점 (상위 3항목)")
        for d in top3:
            meta  = items_meta.get(d["item_key"], {})
            r     = rows_by_key.get(d["item_key"], {})
            score = r.get("score")
            color = _item_color(score)
            st.markdown(
                f"<div style='padding:10px 0;border-bottom:1px solid #f1f5f9'>"
                f"<span style='color:#1e293b;font-weight:600'>{meta.get('title', d['item_key'])}</span>"
                f"&nbsp;&nbsp;<span style='color:{color};font-weight:700'>{score}점</span>"
                + (f"<br><span style='font-size:12px;color:#64748b'>{r.get('verdict','')}</span>"
                   if r.get('verdict') else "")
                + "</div>",
                unsafe_allow_html=True,
            )

    with cw:
        st.markdown("##### 🔧 개선점 (하위 3항목)")
        for d in bot3:
            meta    = items_meta.get(d["item_key"], {})
            r       = rows_by_key.get(d["item_key"], {})
            score   = r.get("score")
            color   = _item_color(score)
            comment = (r.get("comment") or "")[:60]
            st.markdown(
                f"<div style='padding:10px 0;border-bottom:1px solid #f1f5f9'>"
                f"<span style='color:#1e293b;font-weight:600'>{meta.get('title', d['item_key'])}</span>"
                f"&nbsp;&nbsp;<span style='color:{color};font-weight:700'>{score}점</span>"
                + (f"<br><span style='font-size:12px;color:#64748b'>{comment}</span>"
                   if comment else "")
                + "</div>",
                unsafe_allow_html=True,
            )


# ════════════════════════════════════════════════════════
# TAB 2 · 항목별 상세 + 원문 하이라이트
# ════════════════════════════════════════════════════════
with tab_items:
    st.caption(
        "항목 위에 **마우스를 올리면** 원문에서 평가 근거에 형광펜 표시 · "
        "**클릭하면 고정** (다시 클릭하면 해제)"
    )
    st.markdown("")

    # 전체 항목 요약 테이블
    by_cat_map = by_category()
    table_rows: list[dict] = []
    for ck in sorted(CATEGORIES):
        for item in by_cat_map[ck]:
            r = rows_by_key.get(item["key"], {})
            table_rows.append({
                "카테고리": f"{ck} {CATEGORIES[ck]}",
                "항목": item["title"],
                "중요도": _WEIGHT_LABEL.get(item["weight"], ""),
                "점수": r.get("score", "N/A"),
                "판정": (r.get("verdict") or "")[:80],
            })

    with st.expander("📊 전체 18항목 요약", expanded=False):
        st.dataframe(pd.DataFrame(table_rows), hide_index=True, width="stretch")

    st.markdown("")

    if not lec_chunks:
        st.warning("chunks.jsonl 이 없거나 이 강의의 청크를 찾지 못했습니다.")
    else:
        items_data: list[dict] = []
        for ck in sorted(CATEGORIES):
            for item in by_cat_map[ck]:
                r = rows_by_key.get(item["key"], {})
                items_data.append({
                    "key":      item["key"],
                    "title":    item["title"],
                    "category": item["category"],
                    "weight":   item["weight"],
                    "score":    r.get("score"),
                    "verdict":  r.get("verdict") or "",
                    "evidence": r.get("evidence") or [],
                })

        _highlight_component(items_data, lec_chunks, height=620)


# ════════════════════════════════════════════════════════
# TAB 3 · 추이 분석
# ════════════════════════════════════════════════════════
with tab_trend:
    all_lecs     = scores.get("lectures", {})
    by_date_total = scores.get("summary", {}).get("by_date", {})

    date_cat_acc: dict[str, dict[str, list[float]]] = {}
    for lid, ld in all_lecs.items():
        date = ld.get("date") or lid.split("_")[0]
        date_cat_acc.setdefault(date, {c: [] for c in CATEGORIES})
        for c, v in ld["category_scores"].items():
            date_cat_acc[date][c].append(v)
    dates_sorted = sorted(date_cat_acc)

    st.markdown("##### 종합 강의력 점수 추이")
    if len(by_date_total) < 2:
        st.info("추이 분석은 2개 이상의 날짜 데이터가 필요합니다. 현재 단일 강의가 분석되어 있습니다.")
        if by_date_total:
            d, v = list(by_date_total.items())[0]
            st.metric(d, f"{v}점")
    else:
        st.plotly_chart(_total_trend_fig(by_date_total),
                        width="stretch", config={"displayModeBar": False})

    st.divider()

    st.markdown("##### 카테고리별 점수 추이")
    if len(dates_sorted) < 2:
        st.info("추이 분석은 2개 이상의 날짜 데이터가 필요합니다.")
    else:
        rows_cat = []
        for date in dates_sorted:
            row: dict = {"날짜": date}
            for c in sorted(CATEGORIES):
                vals = date_cat_acc[date].get(c, [])
                row[CATEGORIES[c]] = round(sum(vals) / len(vals), 1) if vals else None
            rows_cat.append(row)

        df_trend = pd.DataFrame(rows_cat).set_index("날짜")
        st.plotly_chart(_cat_trend_fig(df_trend),
                        width="stretch", config={"displayModeBar": False})
        st.markdown("")
        st.dataframe(df_trend, width="stretch")


def main() -> None:
    pass


if __name__ == "__main__":
    main()
