"""사용자 BYO API 키 — 세션 메모리(st.session_state)에만 보관, 디스크 미저장.

분석 실행 순간에만 os.environ + config 백엔드에 주입하고 끝나면 원복.
→ 서버는 키를 절대 영속화하지 않음(요청대로 미저장).
"""
from __future__ import annotations

import contextlib
import os
import threading

import streamlit as st

# 키 주입은 os.environ·config 를 프로세스 전역으로 바꾸므로, 워커풀에서 동시 실행 시
# 서로 덮어쓰지 않게 전역 락으로 직렬화한다(키 컨텍스트는 한 번에 하나만 활성).
_APPLY_LOCK = threading.Lock()

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
    """실행 동안만 키/백엔드를 env+config 에 주입, 종료 시 원복.

    전역 락으로 직렬화 — 워커풀의 동시 job 들이 서로의 키/백엔드를 덮어쓰지 않게 보장.
    (process-global 주입 방식의 안전장치. 진짜 병렬 멀티키 실행은 per-call 키 전달이 필요 — 향후.)
    """
    from src import config
    _APPLY_LOCK.acquire()
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
        _APPLY_LOCK.release()
