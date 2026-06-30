"""학생 설문폼 — 공개 폼(토큰) 생성·응답 수집·집계.

학생은 `?form=<토큰>` URL 만 받아 로그인 없이 평가(종합 만족도 + C1~C5 카테고리, 1~5).
관리자는 응답을 집계해 '실제 사용자 평가' + 'AI vs 학생 비교'로 본다.

저장:
  report.dir/form.json                폼 설정(token·active·created_at)
  report.dir/feedback_responses.jsonl  학생 응답(1행=1명)
  ws_root()/_form_index.json           token → {wid, rid}  (공개 라우트가 토큰으로 보고서 찾기)
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from statistics import mean

from src.analyze.checklist import CATEGORIES

# 종합 만족도 1문항 + 18항목(체크리스트 전체)을 학생이 판단 가능한 문장으로.
# key=AI 항목키(item_key)와 동일 → AI vs 학생 항목별 비교 가능. cat=카테고리.
OVERALL = {"key": "overall", "label": "전반적으로 이 강의에 만족하시나요?"}
ITEMS = [
    {"key": "C1_repetition", "cat": "C1", "label": "불필요한 반복·군더더기 표현이 적었나요?"},
    {"key": "C1_completeness", "cat": "C1", "label": "문장이 끊기지 않고 완결되게 전달됐나요?"},
    {"key": "C1_consistency", "cat": "C1", "label": "말투·호칭이 일관되게 유지됐나요?"},
    {"key": "C2_objective", "cat": "C2", "label": "강의 시작에 오늘 배울 내용·목표를 안내했나요?"},
    {"key": "C2_review", "cat": "C2", "label": "이전 내용을 복습하고 오늘과 연결해 줬나요?"},
    {"key": "C2_structure", "cat": "C2", "label": "개념→예시→실습 흐름이 체계적이었나요?"},
    {"key": "C2_emphasis", "cat": "C2", "label": "중요한 부분을 강조해서 짚어 줬나요?"},
    {"key": "C2_summary", "cat": "C2", "label": "강의 끝에 핵심을 요약·정리해 줬나요?"},
    {"key": "C3_definition", "cat": "C3", "label": "새 개념을 명확하게 정의해 줬나요?"},
    {"key": "C3_term_explanation", "cat": "C3", "label": "전문 용어를 충분히 설명해 줬나요?"},
    {"key": "C3_analogy", "cat": "C3", "label": "비유·예시로 이해를 도왔나요?"},
    {"key": "C3_prerequisite", "cat": "C3", "label": "필요한 선행 개념을 짚고 넘어갔나요?"},
    {"key": "C3_concept_connection", "cat": "C3", "label": "개념들을 서로 연결해 설명했나요?"},
    {"key": "C3_code_explanation", "cat": "C3", "label": "코드를 이유·의도까지 설명해 줬나요?"},
    {"key": "C4_pace", "cat": "C4", "label": "강의 속도가 따라가기 적절했나요?"},
    {"key": "C4_transition", "cat": "C4", "label": "주제가 바뀔 때 전환을 안내해 줬나요?"},
    {"key": "C5_example", "cat": "C5", "label": "예시가 수준에 맞고 실무와 관련 있었나요?"},
    {"key": "C5_practice", "cat": "C5", "label": "이론 설명 후 실습으로 잘 이어졌나요?"},
]
QUESTIONS = [OVERALL] + ITEMS                      # 하위호환(단순 순회)
CAT_KEYS = ["C1", "C2", "C3", "C4", "C5"]
ITEM_KEYS = [q["key"] for q in ITEMS]


def items_by_cat() -> dict:
    """카테고리 → [item dict] (폼 그룹 렌더용)."""
    out: dict = {c: [] for c in CAT_KEYS}
    for it in ITEMS:
        out[it["cat"]].append(it)
    return out


def base_url() -> str:
    """폼 공개 URL 베이스.

    우선순위: ① 환경변수 LECTURE_BASE_URL(예: https://도메인) ② 요청 헤더에서 자동 감지
    (배포 시 Caddy/프록시가 넘기는 Host·X-Forwarded-Proto) ③ 로컬 기본 localhost.
    배포에서 env 미설정이어도 실제 접속 도메인으로 폼 주소가 나오도록 헤더 기반 폴백을 둔다.
    """
    env = os.environ.get("LECTURE_BASE_URL")
    if env:
        return env.rstrip("/")
    try:
        import streamlit as st
        h = st.context.headers or {}
        host = h.get("Host") or h.get("host")
        if host and "localhost" not in host and "127.0.0.1" not in host:
            proto = (h.get("X-Forwarded-Proto") or h.get("x-forwarded-proto")
                     or ("http" if host.startswith(("localhost", "127.")) else "https"))
            return f"{proto}://{host}".rstrip("/")
    except Exception:
        pass
    return "http://localhost:8503"


def _index_path():
    from service.workspace import ws_root
    return ws_root() / "_form_index.json"


def _load_index() -> dict:
    p = _index_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save_index(idx: dict) -> None:
    _index_path().write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 폼 설정 ────────────────────────────────────────────────────────────────
def create_form(report, wid: str, *, now: str = "") -> str:
    """보고서에 공개 폼 생성(이미 있으면 기존 토큰 반환). 전역 인덱스 갱신."""
    existing = load_form(report)
    if existing and existing.get("token"):
        return existing["token"]
    token = secrets.token_urlsafe(8)
    (report.dir / "form.json").write_text(
        json.dumps({"token": token, "active": True, "created_at": now,
                    "title": report.name}, ensure_ascii=False, indent=2), encoding="utf-8")
    idx = _load_index()
    idx[token] = {"wid": wid, "rid": report.report_id}
    _save_index(idx)
    return token


def load_form(report) -> dict | None:
    p = report.dir / "form.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def form_url(report) -> str | None:
    f = load_form(report)
    return f"{base_url()}/?form={f['token']}" if f else None


def set_active(report, active: bool) -> None:
    f = load_form(report) or {}
    f["active"] = active
    (report.dir / "form.json").write_text(json.dumps(f, ensure_ascii=False, indent=2),
                                          encoding="utf-8")


def resolve_token(token: str):
    """token → (wid, rid) | None."""
    e = _load_index().get(token)
    return (e["wid"], e["rid"]) if e else None


# ── 응답 ───────────────────────────────────────────────────────────────────
def add_response(report, resp: dict) -> None:
    """학생 응답 1건 append. resp={overall, C1..C5, comment, ts}."""
    with (report.dir / "feedback_responses.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(resp, ensure_ascii=False) + "\n")


def load_responses(report) -> list[dict]:
    p = report.dir / "feedback_responses.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]


def aggregate(responses: list[dict]) -> dict:
    """응답들 → {n, overall, by_item:{item_key:mean}, by_cat:{C:mean(해당 카테고리 항목 응답)}}."""
    n = len(responses)
    cat_names = {c: CATEGORIES[c] for c in CAT_KEYS}
    if not n:
        return {"n": 0, "overall": None, "by_item": {k: None for k in ITEM_KEYS},
                "by_cat": {c: None for c in CAT_KEYS}, "cat_names": cat_names}

    def m(vals):
        vals = [v for v in vals if isinstance(v, (int, float))]
        return round(mean(vals), 2) if vals else None

    by_item = {k: m([r.get(k) for r in responses]) for k in ITEM_KEYS}
    # 카테고리 = 그 카테고리 항목들의 모든 응답 평균(응답 단위 풀링)
    by_cat = {}
    for c in CAT_KEYS:
        keys = [it["key"] for it in ITEMS if it["cat"] == c]
        vals = [r.get(k) for r in responses for k in keys]
        by_cat[c] = m(vals)
    return {"n": n, "overall": m([r.get("overall") for r in responses]),
            "by_item": by_item, "by_cat": by_cat, "cat_names": cat_names}
