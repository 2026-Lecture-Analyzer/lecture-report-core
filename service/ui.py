"""서비스 UI 디자인 시스템 — 프로덕션급 룩(토스/리니어 계열).

원칙: 흰 배경 · 넉넉한 여백 · 단일 블루 액센트 · 얇은 보더 · 절제된 타이포 · 그림자 최소.
set_page_config 직후 inject_css() 1회. 클래스명은 기존 호출부와 호환.
"""
from __future__ import annotations

import streamlit as st

ACCENT = "#3182f6"

_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

:root{
  --accent:#3182f6; --accent-d:#1b64da; --accent-soft:#eef4ff;
  --bg:#ffffff; --surface:#ffffff; --panel:#fafbfc;
  --border:#edeef1; --border-s:#e3e5e9;
  --text:#191f28; --text-2:#4e5968; --muted:#8b95a1;
}

html, body, [class*="css"], .stApp, button, input, textarea, select{
  font-family:'Pretendard','Pretendard Variable',-apple-system,BlinkMacSystemFont,sans-serif !important;
  -webkit-font-smoothing:antialiased; }
.stApp{ background:var(--bg); color:var(--text); }
#MainMenu, footer, [data-testid="stToolbar"]{ visibility:hidden; }
[data-testid="stHeader"]{ background:transparent; height:0; }
.block-container{ padding-top:2rem; padding-bottom:4rem; max-width:1080px; }

h1,h2,h3,h4{ letter-spacing:-.02em; color:var(--text); font-weight:700; }
[data-testid="stCaptionContainer"], .stCaption{ color:var(--muted) !important; }

/* ── 페이지 헤더(그라데이션 배너 대체) ── */
.page-head{ padding:.2rem 0 1rem; margin-bottom:1.4rem; border-bottom:1px solid var(--border); }
.page-head .ph-t{ font-size:1.55rem; font-weight:800; letter-spacing:-.03em; line-height:1.2; }
.page-head .ph-s{ color:var(--muted); font-size:.9rem; margin-top:.35rem; }
.page-head .ph-accent{ display:inline-block; width:30px; height:3px; border-radius:3px;
  background:var(--accent); margin-bottom:.7rem; }

/* ── 메트릭: 미니멀 카드 ── */
[data-testid="stMetric"]{ background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:1rem 1.1rem; }
[data-testid="stMetricValue"]{ font-weight:800; color:var(--text); font-size:1.55rem; letter-spacing:-.02em; }
[data-testid="stMetricLabel"]{ color:var(--muted); font-weight:500; }
[data-testid="stMetricLabel"] p{ font-size:.82rem; }

[data-testid="stExpander"]{ border:1px solid var(--border); border-radius:12px; background:var(--surface); }
[data-testid="stExpander"] summary{ font-weight:600; color:var(--text-2); }

/* ── 버튼: 솔리드 블루(그라데이션X) / 보조는 화이트 ── */
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
  border-radius:10px; font-weight:600; font-size:.9rem; padding:.5rem 1.05rem;
  border:1px solid var(--border-s); background:#fff; color:var(--text-2); transition:all .12s ease; }
.stButton>button:hover{ border-color:#cdd1d8; background:var(--panel); color:var(--text); }
.stButton>button[kind="primary"], .stFormSubmitButton>button{
  background:var(--accent); color:#fff; border:1px solid var(--accent); box-shadow:none; }
.stButton>button[kind="primary"]:hover{ background:var(--accent-d); border-color:var(--accent-d); color:#fff; }

/* ── 탭: 언더라인 스타일 ── */
.stTabs [data-baseweb="tab-list"]{ gap:1.3rem; border-bottom:1px solid var(--border); }
.stTabs [data-baseweb="tab"]{ height:42px; padding:0 .1rem; background:transparent !important;
  color:var(--muted); font-weight:600; font-size:.92rem; border-radius:0; }
.stTabs [data-baseweb="tab"]:hover{ color:var(--text-2); }
.stTabs [aria-selected="true"]{ color:var(--accent) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--accent); height:2.5px; }

/* ── 사이드바 ── */
[data-testid="stSidebar"]{ background:var(--panel); border-right:1px solid var(--border); }
[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }

/* ── 입력/표 ── */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-baseweb="select"]>div{
  border-radius:10px !important; border-color:var(--border-s) !important; }
[data-testid="stTextInput"] input:focus{ border-color:var(--accent) !important; }
[data-testid="stDataFrame"]{ border:1px solid var(--border); border-radius:12px; }
[data-testid="stAlert"]{ border-radius:12px; border:1px solid var(--border); }
hr{ margin:1rem 0; border-color:var(--border); }
[data-testid="stProgress"]>div>div>div{ background:var(--accent); }

/* ── 코칭/강점 카드 ── */
.sec-h{ font-size:1.05rem; font-weight:800; letter-spacing:-.02em; margin:1.5rem 0 .6rem; }
.coach-strength{ display:inline-block; background:var(--panel); color:var(--text-2);
  border:1px solid var(--border-s); border-radius:8px; padding:.4rem .75rem; margin:.2rem .4rem .2rem 0;
  font-size:.85rem; font-weight:600; }
.coach-strength b{ color:var(--accent-d); }

.pri-card{ background:var(--surface); border:1px solid var(--border); border-radius:14px;
  padding:1.15rem 1.25rem; margin:.8rem 0; }
.pri-head{ display:flex; align-items:center; gap:.55rem; flex-wrap:wrap; }
.pri-head .num{ color:var(--muted); font-weight:800; font-size:.95rem; }
.pri-head .t{ font-size:1.05rem; font-weight:800; letter-spacing:-.02em; }
.badge{ border-radius:7px; padding:.12rem .5rem; font-size:.78rem; font-weight:700; }
.tagw{ background:var(--panel); color:var(--muted); border:1px solid var(--border-s);
  border-radius:7px; padding:.1rem .5rem; font-size:.74rem; font-weight:600; }
.pri-desc{ color:var(--text-2); font-size:.88rem; margin:.5rem 0 .8rem; }
.evi-lab{ font-size:.76rem; color:var(--muted); font-weight:600; margin:.2rem 0 .35rem;
  text-transform:uppercase; letter-spacing:.04em; }
.evi{ background:var(--panel); border:1px solid var(--border); border-radius:10px;
  padding:.55rem .75rem; margin:.35rem 0; font-size:.88rem; line-height:1.55; color:var(--text-2); }
.evi .tag{ display:inline-block; background:#fff; color:var(--muted); border:1px solid var(--border-s);
  border-radius:6px; padding:0 .42rem; font-size:.72rem; font-weight:600; margin-right:.45rem; }
.coach-box{ background:var(--accent-soft); border:1px solid #dbe7ff; border-left:3px solid var(--accent);
  border-radius:10px; padding:.7rem .9rem; margin:.7rem 0 .4rem; font-size:.89rem; color:var(--text-2); }
.coach-box .lab{ font-weight:700; color:var(--accent-d); font-size:.76rem;
  text-transform:uppercase; letter-spacing:.04em; }
.ment{ display:block; background:var(--panel); border:1px solid var(--border-s); border-radius:9px;
  padding:.45rem .7rem; margin:.28rem 0; font-size:.88rem; color:var(--text); }

/* ── 랜딩 ── */
.feat{ background:var(--surface); border:1px solid var(--border); border-radius:16px;
  padding:1.4rem 1.15rem; height:100%; text-align:left; transition:border-color .12s ease; }
.feat:hover{ border-color:var(--accent); }
.feat b{ display:block; font-size:1rem; font-weight:700; margin:.3rem 0 .4rem; color:var(--text); }
.feat span{ color:var(--muted); font-size:.86rem; line-height:1.5; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str = "", icon: str = "") -> None:
    """클린 페이지 헤더(그라데이션 배너 아님) — 액센트 바 + 타이틀 + 메타."""
    sub = f'<div class="ph-s">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="page-head"><div class="ph-accent"></div>'
        f'<div class="ph-t">{title}</div>{sub}</div>',
        unsafe_allow_html=True,
    )
