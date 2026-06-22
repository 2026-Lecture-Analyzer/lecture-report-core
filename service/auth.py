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
    st.button("🔐 Google로 로그인", type="primary",
              on_click=lambda: st.login("google"))


def logout_button() -> None:
    if _dev_user():
        st.caption("개발 모드 로그인 (LECTURE_DEV_USER)")
        return
    st.button("로그아웃", on_click=st.logout)


def require_login() -> dict:
    """로그인 강제. 안 했으면 로그인 화면 띄우고 중단."""
    user = current_user()
    if user:
        return user
    st.title("🎓 강의력 분석 서비스")
    st.write("구글 계정으로 로그인해 워크스페이스를 시작하세요.")
    login_button()
    st.stop()
