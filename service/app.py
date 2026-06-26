"""강의력 분석 서비스 (멀티테넌트) — 구글 로그인 · 워크스페이스 · BYO 키.

실행(로컬): core/.venv/bin/streamlit run service/app.py --server.port 8503
  로컬 테스트 로그인: LECTURE_DEV_USER=me@x.com streamlit run ...
배포: Docker + Caddy(도메인·TLS), .streamlit/secrets.toml 에 구글 OIDC. deploy/ 참고.

흐름:
  로그인 → 워크스페이스(생성 / 초대링크로 합류 / 선택)
       → 내 API 키 입력(세션에만) → 📂 보고서 보기 / ➕ 분석 추가
  보고서·파일은 워크스페이스별로 격리 저장, 용량제한 적용.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service import auth, keys as keymod, pipeline, workspace as wsmod
from service.report_view import render_report
from service.store import create_report, delete_report, list_reports, load_report

st.set_page_config(page_title="강의력 분석 서비스", page_icon="🎓", layout="wide")
NEW = "__new__"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f}MB"


# ── 로그인 게이트 ──
user = auth.require_login()

# ── 초대링크 처리 (?invite=토큰) ──
invite_tok = st.query_params.get("invite")
if invite_tok:
    ws = wsmod.accept_invite(invite_tok, user, now=_now())
    if ws:
        st.session_state["active_ws"] = ws.wid
        st.toast(f"'{ws.name}' 워크스페이스에 합류했어요!")
    else:
        st.warning("유효하지 않은 초대 링크예요.")
    st.query_params.clear()

my_ws = wsmod.list_workspaces_for(user["uid"])

# ══ 사이드바 ══
with st.sidebar:
    st.title("🎓 강의력 분석")
    st.caption(f"👤 {user['name']} · {user['email']}")
    auth.logout_button()
    st.divider()

    # 워크스페이스 선택
    active_wid = st.session_state.get("active_ws")
    if my_ws:
        wids = [w.wid for w in my_ws]
        idx = wids.index(active_wid) if active_wid in wids else 0
        sel = st.selectbox("워크스페이스", wids, index=idx,
                           format_func=lambda wid: next(w.name for w in my_ws if w.wid == wid))
        st.session_state["active_ws"] = sel
        active_wid = sel
    else:
        active_wid = None

    with st.expander("➕ 새 워크스페이스 / 🔗 초대 합류"):
        nw = st.text_input("새 워크스페이스 이름", placeholder="예: ○○교육원")
        if st.button("워크스페이스 생성", disabled=not nw.strip()):
            ws = wsmod.create_workspace(nw.strip(), user, now=_now())
            st.session_state["active_ws"] = ws.wid
            st.rerun()
        tok = st.text_input("초대 코드", placeholder="초대받은 코드 입력")
        if st.button("코드로 합류", disabled=not tok.strip()):
            ws = wsmod.accept_invite(tok.strip(), user, now=_now())
            if ws:
                st.session_state["active_ws"] = ws.wid
                st.rerun()
            else:
                st.error("유효하지 않은 코드")

    st.divider()
    keymod.key_form()

# ── 워크스페이스 없으면 온보딩 ──
if not active_wid:
    st.markdown(
        """
        <style>.block-container {max-width:920px;}</style>
        <div style="text-align:center; margin:1.5rem 0 1rem;">
          <div style="font-size:3.2rem; line-height:1;">🚀</div>
          <h1 style="margin:.4rem 0 .2rem;">워크스페이스를 만들어 시작하세요</h1>
          <p style="color:#64748b; font-size:1.02rem;">
            워크스페이스는 보고서를 모아두고 팀과 공유하는 공간이에요.
            새로 만들거나, 받은 초대 코드로 합류하세요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown("#### ➕ 새 워크스페이스 만들기")
        nw = st.text_input("워크스페이스 이름", placeholder="예: ○○교육원", key="onb_new")
        if st.button("만들기", type="primary", use_container_width=True,
                     disabled=not nw.strip()):
            ws = wsmod.create_workspace(nw.strip(), user, now=_now())
            st.session_state["active_ws"] = ws.wid
            st.rerun()
    st.markdown("<p style='text-align:center; color:#94a3b8; margin:.6rem 0;'>또는</p>",
                unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("#### 🔗 초대 코드로 합류")
        tok = st.text_input("초대 코드", placeholder="동료에게 받은 코드", key="onb_tok")
        if st.button("합류하기", use_container_width=True, disabled=not tok.strip()):
            ws = wsmod.accept_invite(tok.strip(), user, now=_now())
            if ws:
                st.session_state["active_ws"] = ws.wid
                st.rerun()
            else:
                st.error("유효하지 않은 코드예요.")
    st.stop()

ws = wsmod.load_workspace(active_wid)
RBASE = ws.reports_dir  # 이 워크스페이스의 보고서 폴더(격리)

# ── 워크스페이스 헤더 + 용량 ──
used, quota = ws.usage_bytes(), ws.quota_bytes
st.markdown(f"### 🗂️ {ws.name}　<span style='color:#888;font-size:0.6em'>"
            f"멤버 {len(ws.members)}명 · 내 권한 {ws.role(user['uid'])}</span>",
            unsafe_allow_html=True)
qc1, qc2 = st.columns([3, 1])
qc1.progress(min(used / quota, 1.0), text=f"저장 용량 {_mb(used)} / {_mb(quota)}")
mode = qc2.radio("작업", ["📂 보고서 보기", "➕ 분석 추가"], label_visibility="collapsed")

reports = list_reports(RBASE)

# ══════════════════════════════════════════════════════════════════════
# 보고서 보기
# ══════════════════════════════════════════════════════════════════════
if mode.startswith("📂"):
    if not reports:
        st.info("이 워크스페이스엔 아직 보고서가 없습니다. **➕ 분석 추가**로 첫 강의를 올려보세요.")
    else:
        names = {f"{r.name}  ·  {len(r.sessions)}세션": r.report_id for r in reports}
        sel = st.selectbox("보고서 선택", list(names))
        rpt = load_report(names[sel], RBASE)
        render_report(rpt)
        with st.expander("⚙️ 이 보고서 관리"):
            if st.checkbox("이 보고서 삭제하기", key="del_chk") and \
               st.button("🗑️ 영구 삭제", type="primary"):
                delete_report(rpt.report_id, RBASE)
                st.success(f"'{rpt.name}' 삭제됨")
                st.rerun()

    # 멤버 초대
    with st.expander("👥 워크스페이스 공유 (초대 링크)"):
        st.caption("초대 코드를 만들어 동료에게 보내면, 그 사람이 같은 워크스페이스에 합류해 보고서를 공유합니다.")
        if st.button("초대 코드 생성"):
            tok = ws.create_invite(user["uid"], now=_now())
            st.session_state["last_invite"] = tok
        tok = st.session_state.get("last_invite")
        if tok:
            st.code(tok, language=None)
            st.caption("또는 링크로:")
            st.code(f"https://lectureAnalzer.yeseulkim.cloud/?invite={tok}", language=None)

# ══════════════════════════════════════════════════════════════════════
# 분석 추가
# ══════════════════════════════════════════════════════════════════════
else:
    st.subheader("➕ 강의 분석 추가")
    if not keymod.has_keys():
        st.warning("분석하려면 먼저 왼쪽 사이드바에서 **내 API 키**를 입력하세요.")
    if ws.over_quota():
        st.error(f"저장 용량을 초과했습니다({_mb(used)}/{_mb(quota)}). 보고서를 정리한 뒤 추가하세요.")

    opts = {NEW: "🆕 새 보고서 만들기 (별개 강의)"}
    opts.update({r.report_id: f"📎 기존에 합치기 — {r.name}" for r in reports})
    target = st.radio("어디에 추가할까요?", list(opts), format_func=lambda k: opts[k])

    if target == NEW:
        c1, c2 = st.columns([2, 1])
        new_name = c1.text_input("보고서(강의) 이름", placeholder="예: 클라우드 컴퓨팅 기초 — AWS 입문")
        new_inst = c2.text_input("강사명 (선택)")
        mode_label = st.radio("세션 분리 방식", ["오전/오후 분리", "단일 강사"], horizontal=True,
                              help="오전/오후 분리: 강의 시각(13시 기준)으로 두 세션. 단일 강사: 한 세션(종일).")
        sess_mode = "ampm" if mode_label.startswith("오전") else "single"
    else:
        rpt0 = load_report(target, RBASE)
        new_name, new_inst = "", ""
        sess_mode = rpt0.mode
        st.info(f"**{rpt0.name}** 에 합칩니다 — 세션 모드: "
                f"**{'오전/오후 분리' if sess_mode == 'ampm' else '단일 강사'}**")

    st.divider()
    files = st.file_uploader("강의 스크립트 txt 업로드 (여러 개 가능)", type=["txt"],
                             accept_multiple_files=True)
    st.caption("⚙️ 실제 Upstage/Gemini 분석을 실행합니다 — 과금·수 분 소요(키는 본인 것).")
    sc = st.slider("self-consistency (분석 반복수, 높을수록 정확·비쌈)", 1, 5, 3)

    file_meta = []
    if files:
        import re as _re
        st.markdown("##### 파일별 정보")
        for i, f in enumerate(files):
            cols = st.columns([3, 2, 3])
            cols[0].markdown(f"📄 **{f.name}**")
            m = _re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
            date = cols[1].text_input("날짜(YYYY-MM-DD)", value=m.group(1) if m else "", key=f"date_{i}")
            subject = cols[2].text_input("과목/주제(선택)", key=f"subj_{i}")
            file_meta.append({"file": f, "date": date, "subject": subject})

    can_run = (bool(files) and keymod.has_keys() and not ws.over_quota()
               and (target != NEW or new_name.strip())
               and all(fm["date"].strip() for fm in file_meta))
    if st.button("🚀 분석 실행", type="primary", disabled=not can_run):
        if target == NEW:
            rpt = create_report(new_name.strip(), instructor=new_inst.strip(),
                                mode=sess_mode, created_at=_now(), base=RBASE)
            st.success(f"새 보고서 생성: **{rpt.name}**")
        else:
            rpt = load_report(target, RBASE)
        course = rpt.report_id

        progress = st.progress(0.0)
        total, all_added = len(file_meta), []
        for i, fm in enumerate(file_meta):
            raw = fm["file"].read().decode("utf-8", errors="replace")
            st.write(f"**[{i+1}/{total}] {fm['file'].name}** 처리 중…")
            logs, lines = st.empty(), []

            def log(msg, _logs=logs, _lines=lines):
                _lines.append(str(msg))
                _logs.code("\n".join(_lines))

            try:
                if ws.over_quota():
                    raise RuntimeError("저장 용량 초과 — 추가 중단")
                with keymod.applied(keymod.get_keys()):
                    grouped = pipeline.run_real(raw, date=fm["date"], course=course,
                                                mode=sess_mode, self_consistency=sc, log=log)
                added = pipeline.ingest(rpt, grouped, subject=fm["subject"],
                                        source_file=fm["file"].name, added_at=_now())
                all_added += added
                log(f"✅ 세션 추가: {added}")
            except Exception as e:
                log(f"❌ 실패: {type(e).__name__}: {e}")
                st.exception(e)
            progress.progress((i + 1) / total)

        if all_added:
            st.success(f"완료! **{rpt.name}** 에 세션 {len(all_added)}개 추가 — **📂 보고서 보기**에서 확인하세요.")
            st.balloons()
