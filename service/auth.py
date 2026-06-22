"""구글 로그인 — Streamlit 네이티브 OIDC(st.login/st.user) 래퍼.

배포: .streamlit/secrets.toml 의 [auth] 에 구글 OIDC 설정(아래 secrets.toml.example).
로컬 개발: 환경변수 LECTURE_DEV_USER=email 로 OIDC 없이 가짜 로그인(테스트용).

사용자 식별자(uid)는 구글 sub(없으면 email). 워크스페이스 소유/멤버십 키로 쓴다.
"""
from __future__ import annotations

import os

import streamlit as st


def _dev_user() -> dict | None:
    email = os.environ.get("LECTURE_DEV_USER")
    if not email:
        return None
    return {"uid": f"dev:{email}", "email": email,
            "name": email.split("@")[0], "dev": True}


def current_user() -> dict | None:
    """로그인된 사용자 {uid,email,name} 또는 None."""
    dev = _dev_user()
    if dev:
        return dev
    try:
        if getattr(st.user, "is_logged_in", False):
            sub = getattr(st.user, "sub", None) or st.user.email
            return {"uid": str(sub), "email": st.user.email,
                    "name": getattr(st.user, "name", None) or st.user.email, "dev": False}
    except Exception:
        # secrets[auth] 미설정 등 — 비로그인 취급
        return None
    return None


def login_button() -> None:
    st.button("🔐 Google로 로그인", type="primary", use_container_width=True,
              on_click=lambda: st.login("google"))


def logout_button() -> None:
    if _dev_user():
        st.caption("🧪 개발 모드 로그인 (LECTURE_DEV_USER)")
        return
    st.button("🔓 로그아웃", on_click=st.logout, use_container_width=True)


def require_login() -> dict:
    """로그인 강제. 안 했으면 랜딩+로그인 화면 띄우고 중단."""
    user = current_user()
    if user:
        return user
    _render_landing()
    st.stop()


# 랜딩 카드(아이콘, 제목, 설명)
_FEATURES = [
    ("📂", "워크스페이스 협업", "팀을 초대해 보고서를 함께 보고 관리"),
    ("🧠", "항목별 품질 분석", "개념 설명·구조·상호작용 등 다면 평가"),
    ("🔑", "내 API 키", "키는 세션에만 — 서버에 저장하지 않아요"),
]


def _render_landing() -> None:
    """비로그인 랜딩 — 히어로 + 기능 카드 + 구글 로그인 CTA."""
    st.markdown(
        """
        <style>
          [data-testid="stSidebar"], [data-testid="stHeader"] {display:none;}
          #MainMenu, footer {visibility:hidden;}
          .block-container {padding-top:3.5rem; max-width:780px;}
          .login-hero {text-align:center;}
          .login-hero .logo {font-size:3.6rem; line-height:1;}
          .login-hero h1 {font-size:2.5rem; letter-spacing:-.02em; margin:.4rem 0 .2rem;}
          .login-hero p {color:#64748b; font-size:1.05rem; margin:.2rem 0 1.8rem;}
          .feat {background:#f8fafc; border:1px solid #e2e8f0; border-radius:14px;
                 padding:1.1rem 1rem; height:100%; text-align:center;}
          .feat b {display:block; font-size:.98rem; margin:.2rem 0 .3rem;}
          .feat span {color:#64748b; font-size:.86rem; line-height:1.4;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="login-hero">
          <div class="logo">🎓</div>
          <h1>강의력 분석 서비스</h1>
          <p>강의 스크립트를 올리면 AI가 강의 품질을 항목별로 분석해 보고서로 만들어 드립니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for col, (icon, title, desc) in zip(st.columns(3), _FEATURES):
        col.markdown(
            f'<div class="feat"><b>{icon} {title}</b><span>{desc}</span></div>',
            unsafe_allow_html=True,
        )
    st.write("")
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        login_button()
        st.caption("구글 계정으로 로그인해 시작하세요.")
