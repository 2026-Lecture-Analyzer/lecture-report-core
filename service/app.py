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
from service import auth, jobs, keys as keymod, pipeline, ui, workspace as wsmod
from service.report_view import render_report
from service.store import create_report, delete_report, list_reports, load_report

st.set_page_config(page_title="강의력 분석 서비스", page_icon="🎓", layout="wide")
ui.inject_css()
NEW = "__new__"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f}MB"


class _UploadShim:
    """워커 스레드에서 업로드 객체 흉내(이름+bytes만) — STT 입력용."""
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def _analyze_job(payload: dict, keys: dict, rpt, course: str, mode: str, sc: int, *, log):
    """워커가 실행하는 분석 작업 — (음성→STT)→정제·분석→보고서 반영. 전부 키락 안에서 직렬화."""
    with keymod.applied(keys):                      # 전역 키락(동시 job 안전) + BYO 키 주입
        if payload["is_media"]:
            log("🎙️ STT 전사 (Gemini, 과금)…")
            raw = pipeline.audio_to_transcript(
                _UploadShim(payload["name"], payload["bytes"]),
                date=payload["date"], course=course, log=log)
        else:
            raw = payload["bytes"].decode("utf-8", errors="replace")
        grouped = pipeline.run_real(raw, date=payload["date"], course=course,
                                    mode=mode, self_consistency=sc, log=log)
        added = pipeline.ingest(rpt, grouped, subject=payload["subject"],
                                source_file=payload["name"], added_at=_now())
    log(f"✅ 세션 추가: {added}")
    return added


_JOB_ICON = {"queued": "⏳", "running": "⚙️", "done": "✅", "error": "❌"}


@st.fragment(run_every=2)
def _render_jobs() -> None:
    """작업 현황 패널 — 2초마다 자동 갱신(폴링)."""
    ids = st.session_state.get("job_ids", [])
    js = jobs.get_many(ids)
    if not js:
        return
    s = jobs.queue_stats()
    st.markdown('<div class="sec-h">작업 현황</div>', unsafe_allow_html=True)
    cc = st.columns([4, 1])
    cc[0].caption(f"워커 {s['workers']} · 대기 {s['queued']} · 진행 {s['running']} · "
                  f"완료 {s['done']} · 실패 {s['error']}")
    if cc[1].button("완료 정리", key="clr_jobs"):
        jobs.clear_finished(ids)
        st.session_state["job_ids"] = [j.id for j in jobs.get_many(ids)]
        st.rerun()
    for j in js:
        with st.expander(f"{_JOB_ICON.get(j.status,'•')} {j.name} · {j.status} · {j.elapsed:.0f}s",
                         expanded=(j.status == "running")):
            if j.logs:
                st.code("\n".join(j.logs[-12:]))
            if j.status == "error":
                st.error(j.error)


def _render_public_form(token: str) -> None:
    """공개 학생 평가 폼(로그인 불필요) — ?form=<토큰> 으로 진입. 제출 후 stop."""
    from service import feedback_forms as ff
    ui.hero("강의 평가", "수강하신 강의를 항목별로 평가해 주세요 · 1~5점", icon="📝")
    res = ff.resolve_token(token)
    if not res:
        st.error("유효하지 않은 평가 링크입니다."); st.stop()
    wid, rid = res
    ws = wsmod.load_workspace(wid)
    rpt = load_report(rid, ws.reports_dir) if ws else None
    form = ff.load_form(rpt) if rpt else None
    if not rpt or not form:
        st.error("평가 폼을 찾을 수 없습니다."); st.stop()
    if not form.get("active", True):
        st.info("이 평가는 마감되었습니다. 참여해 주셔서 감사합니다."); st.stop()

    st.subheader(f"📋 {rpt.name}")
    if rpt.meta.get("instructor"):
        st.caption(f"강사: {rpt.meta['instructor']}")
    st.write("아래 항목을 평가해 주세요.  **1 = 전혀 아니다 ~ 5 = 매우 그렇다**")
    with st.form("student_eval"):
        answers = {"overall": st.slider(f"⭐ {ff.OVERALL['label']}", 1, 5, 3)}
        ibc = ff.items_by_cat()
        for c in ff.CAT_KEYS:
            st.markdown(f"**{c}. {ff.CATEGORIES[c]}**")
            for it in ibc[c]:
                answers[it["key"]] = st.slider(it["label"], 1, 5, 3, key=f"q_{it['key']}")
        comment = st.text_area("자유 의견(선택)", "")
        submitted = st.form_submit_button("제출하기", type="primary")
    if submitted:
        ff.add_response(rpt, {**answers, "comment": comment.strip(), "ts": _now()})
        st.success("평가가 제출되었습니다. 감사합니다! 🙏")
        st.balloons()
    st.stop()


# ── 공개 폼 라우트(로그인 전) ──
_form_tok = st.query_params.get("form")
if _form_tok:
    _render_public_form(_form_tok)

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

# ── 헤더 배너 + 용량 ──
ui.hero(ws.name,
        f"강의력 분석 · AI 코칭 · 멤버 {len(ws.members)}명 · 내 권한 {ws.role(user['uid'])}")
used, quota = ws.usage_bytes(), ws.quota_bytes
qc1, qc2 = st.columns([3, 1])
qc1.progress(min(used / quota, 1.0), text=f"저장 용량 {_mb(used)} / {_mb(quota)}")
mode = qc2.radio("작업", ["📂 보고서 보기", "➕ 분석 추가"], label_visibility="collapsed")

# 작업 현황(워커풀) — 진행 중 job 있으면 자동 폴링 표시
if st.session_state.get("job_ids"):
    _render_jobs()

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
            st.code(f"https://lectureanalzer.yeseulkim.cloud/?invite={tok}", language=None)

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
    files = st.file_uploader(
        "강의 스크립트(txt) 또는 🎙️ 녹음 파일(mp3·m4a·wav·mp4 …) 업로드 — 여러 개 가능",
        type=["txt", "mp3", "m4a", "wav", "aac", "flac", "ogg",
              "mp4", "mov", "mkv", "webm", "m4v"],
        accept_multiple_files=True)
    st.caption("⚙️ 녹음 파일은 먼저 Gemini로 STT 전사 후 분석합니다 — 과금·수 분 소요(키는 본인 것). "
               "음성 STT는 Google(Gemini) 키 필요.")
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
    st.caption(f"🧵 업로드하면 즉시 **작업 큐**에 들어가고 백그라운드 워커({jobs.POOL_SIZE}개)가 처리합니다 — "
               "화면이 멈추지 않고, 다른 작업도 계속 가능합니다.")
    if st.button("🚀 분석 실행 (큐에 추가)", type="primary", disabled=not can_run):
        if target == NEW:
            rpt = create_report(new_name.strip(), instructor=new_inst.strip(),
                                mode=sess_mode, created_at=_now(), base=RBASE)
        else:
            rpt = load_report(target, RBASE)
        course = rpt.report_id
        keys = keymod.get_keys()
        new_ids = []
        for fm in file_meta:
            fobj = fm["file"]
            payload = {"name": fobj.name, "bytes": fobj.getvalue(),
                       "is_media": pipeline.is_media_name(fobj.name),
                       "date": fm["date"], "subject": fm["subject"]}
            jid = jobs.submit(fobj.name, _analyze_job, payload, keys, rpt, course, sess_mode, sc)
            new_ids.append(jid)
        st.session_state["job_ids"] = new_ids + st.session_state.get("job_ids", [])
        st.success(f"✅ {len(new_ids)}개 작업을 큐에 추가했습니다. 상단 **작업 현황**에서 진행 상황을 확인하세요.")
        st.toast("작업이 큐에 들어갔어요 — 백그라운드에서 처리됩니다.")
