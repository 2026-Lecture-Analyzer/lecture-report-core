"""사용자 BYO API 키 — 세션 메모리(st.session_state)에만 보관, 디스크 미저장.

분석 실행 순간에만 os.environ + config 백엔드에 주입하고 끝나면 원복.
→ 서버는 키를 절대 영속화하지 않음(요청대로 미저장).
"""
from __future__ import annotations

import contextlib
import os

import streamlit as st

SS_KEY = "byok"


def get_keys() -> dict | None:
    return st.session_state.get(SS_KEY)


def has_keys() -> bool:
    k = get_keys()
    return bool(k and ((k["backend"] == "upstage" and k.get("upstage_key"))
                       or (k["backend"] == "google" and k.get("google_key"))))


def key_form() -> None:
    """사이드바/본문용 키 입력 폼. 저장은 세션에만."""
    cur = get_keys() or {}
    with st.form("byok_form"):
        st.markdown("##### 🔑 내 API 키 (이 세션에만 보관 · 저장 안 함)")
        backend = st.radio("LLM 제공자", ["upstage", "google"], horizontal=True,
                           index=0 if cur.get("backend", "upstage") == "upstage" else 1,
                           format_func=lambda b: "Upstage Solar" if b == "upstage" else "Google Gemini")
        upstage = st.text_input("UPSTAGE_API_KEY", type="password",
                                value=cur.get("upstage_key", ""))
        google = st.text_input("GOOGLE_API_KEY (Gemini)", type="password",
                               value=cur.get("google_key", ""))
        if st.form_submit_button("키 적용", type="primary"):
            st.session_state[SS_KEY] = {"backend": backend, "upstage_key": upstage.strip(),
                                        "google_key": google.strip()}
            st.success("키 적용됨 (세션에만 보관).")
            st.rerun()
    if has_keys():
        st.caption(f"✅ 현재 제공자: **{get_keys()['backend']}**")
    else:
        st.caption("⚠️ 분석하려면 위에 키를 입력하세요.")


@contextlib.contextmanager
def applied(keys: dict):
    """실행 동안만 키/백엔드를 env+config 에 주입, 종료 시 원복."""
    from src import config
    saved_env = {k: os.environ.get(k) for k in ("UPSTAGE_API_KEY", "GOOGLE_API_KEY")}
    saved_cfg = (config.LLM_BACKEND, config.MODEL_BACKEND, config.EMBED_BACKEND)
    backend = keys["backend"]
    if keys.get("upstage_key"):
        os.environ["UPSTAGE_API_KEY"] = keys["upstage_key"]
    if keys.get("google_key"):
        os.environ["GOOGLE_API_KEY"] = keys["google_key"]
    config.LLM_BACKEND = config.MODEL_BACKEND = config.EMBED_BACKEND = backend
    try:
        yield
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config.LLM_BACKEND, config.MODEL_BACKEND, config.EMBED_BACKEND = saved_cfg
