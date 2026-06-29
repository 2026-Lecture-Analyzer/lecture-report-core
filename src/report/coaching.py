"""강사별 맞춤 코칭 리포트 — 여러 세션 분석을 집계해 개선 코칭을 생성.

기존 강의별 리포트(build.py)가 '한 강의 진단'이라면, 코칭 리포트는 **한 강사의 여러 강의**를
가로질러 (1) 꾸준한 강점 (2) 가중 결손이 큰 개선 우선순위 (3) 주차 추이 를 뽑고, 우선순위
항목마다 **실제 근거 발화/메트릭을 넣어 LLM이 구체 코칭(진단·개선법·바로 쓸 멘트)** 을 쓴다.

설계: 집계·우선순위 선정은 순수 함수(LLM 무관, 테스트 용이). LLM 은 코칭 서술에만 generate_fn
주입으로 사용 → 키 없이 smoke 검증 가능(scripts/smoke_coaching.py).
"""
from __future__ import annotations

import json
from statistics import mean, pstdev

from src.analyze.checklist import CATEGORIES, WEIGHT_VALUE, by_key
from src.refine.jsonout import extract_json

_SESSION_ORDER = {"오전": 0, "오후": 1, "종일": 0}


def _sess_key(date: str, session: str) -> tuple:
    return (date, _SESSION_ORDER.get(session, 0))


# ── 집계(순수) ─────────────────────────────────────────────────────────────
def aggregate(rows: list[dict]) -> dict:
    """분석행(여러 세션) → 항목별 집계.

    반환 item_key → {title, category, weight, weight_v, n, mean, std, trend,
                     series:[(date,session,score)], evidence:[...], comments:[...]}.
    score=None(N/A) 은 평균에서 제외.
    """
    meta = by_key()
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(r["item_key"], []).append(r)

    out: dict[str, dict] = {}
    for key, items in buckets.items():
        m = meta.get(key, {})
        items = sorted(items, key=lambda r: _sess_key(r["date"], r["session"]))
        series = [(r["date"], r["session"], r.get("score")) for r in items]
        scores = [s for _, _, s in series if isinstance(s, (int, float))]
        if not scores:
            continue
        ev, comments = [], []
        for r in items:
            for e in (r.get("evidence") or []):
                q = e.get("quote") if isinstance(e, dict) else str(e)
                if q:
                    ev.append({"date": r["date"], "session": r["session"], "quote": q,
                               "score": r.get("score")})
            c = (r.get("comment") or "").strip()
            if c:
                comments.append({"date": r["date"], "session": r["session"],
                                 "comment": c, "score": r.get("score")})
        out[key] = {
            "title": m.get("title", key), "category": m.get("category", key[:2]),
            "weight": m.get("weight", "mid"),
            "weight_v": WEIGHT_VALUE.get(m.get("weight", "mid"), 2),
            "description": m.get("description", ""),
            "n": len(scores), "mean": round(mean(scores), 2),
            "std": round(pstdev(scores), 2) if len(scores) > 1 else 0.0,
            "trend": _trend(scores), "series": series,
            "evidence": ev, "comments": comments,
        }
    return out


def _trend(scores: list[float]) -> float:
    """뒤 1/3 평균 − 앞 1/3 평균(>0 개선, <0 하락). 표본 적으면 0."""
    n = len(scores)
    if n < 3:
        return 0.0
    t = max(1, n // 3)
    return round(mean(scores[-t:]) - mean(scores[:t]), 2)


def category_summary(agg: dict) -> dict:
    """카테고리별 (가중)평균점수(1~5)."""
    cats: dict[str, list[tuple]] = {}
    for it in agg.values():
        cats.setdefault(it["category"], []).append((it["mean"], it["weight_v"]))
    out = {}
    for c, pairs in cats.items():
        wsum = sum(w for _, w in pairs) or 1
        out[c] = {"name": CATEGORIES.get(c, c),
                  "score": round(sum(m * w for m, w in pairs) / wsum, 2)}
    return out


def pick_priorities(agg: dict, k: int = 3) -> list[dict]:
    """개선 우선순위 — 가중 결손 deficit = weight_v*(5-mean) 큰 순. 동점이면 mean↓·std↑.

    '중요(weight 높음)한데 점수 낮은' 항목을 위로. 꾸준히 낮음(std 작음)도 가산.
    """
    scored = []
    for key, it in agg.items():
        deficit = it["weight_v"] * (5 - it["mean"])
        scored.append((deficit, -it["mean"], it["std"], key, it))
    scored.sort(key=lambda x: (-x[0], x[1], -x[2]))
    return [{"key": key, "deficit": round(d, 2), **it} for d, _, _, key, it in scored[:k]]


def pick_strengths(agg: dict, k: int = 3) -> list[dict]:
    """강점 — 평균 높은 순(동점이면 weight 높은 것 우선)."""
    scored = sorted(agg.items(), key=lambda kv: (-kv[1]["mean"], -kv[1]["weight_v"]))
    return [{"key": key, **it} for key, it in scored[:k]]


# ── 코칭 서술(LLM) ─────────────────────────────────────────────────────────
_COACH_SYS = (
    "너는 IT 강의 코치다. 강사의 실제 강의 데이터(점수·근거 발화)를 보고, 비난이 아니라 "
    "구체적이고 실행 가능한 개선 코칭을 한국어로 제시한다. 막연한 조언 금지 — 근거에 입각해 "
    "'무엇을 어떻게' 바꿀지와 바로 쓸 수 있는 멘트 예시를 준다."
)


def coaching_prompt(item: dict, agg_item: dict, evidence: list[dict]) -> list[dict]:
    """우선순위 1항목에 대한 코칭 생성 메시지. evidence 는 근거 발화/메트릭 코멘트."""
    ev_lines = []
    for e in evidence[:6]:
        tag = f"[{e.get('date','')} {e.get('session','')} {e.get('score','')}점]"
        ev_lines.append(f"- {tag} {e.get('quote') or e.get('comment','')}")
    ev_text = "\n".join(ev_lines) or "(근거 발화 없음 — 해당 항목이 거의 나타나지 않음)"

    user = f"""평가 항목: {agg_item['title']} ({item.get('description','')})
강사 성적: {agg_item['n']}개 세션 평균 {agg_item['mean']}/5 (추이 {agg_item['trend']:+}), 가중치 {agg_item['weight']}.

실제 강의 근거(낮은 세션 위주):
{ev_text}

위 근거에 입각해 코칭을 작성하라. 아래 JSON 하나만 출력(코드펜스 금지):
{{"diagnosis": "현재 무엇이 문제인지 1~2문장(근거 인용)",
  "how_to": "어떻게 개선할지 2~3개 구체 행동",
  "example_lines": ["강의 중 바로 쓸 수 있는 멘트 예시 1", "예시 2"]}}"""
    return [{"role": "system", "content": _COACH_SYS}, {"role": "user", "content": user}]


def _as_lines(v) -> list[str]:
    """문자열 또는 리스트(모델이 둘 중 아무거나 반환) → 줄 리스트로 정규화."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v or "").strip()
    return [s] if s else []


def _coach_one(item_meta: dict, agg_item: dict, generate_fn) -> dict:
    msgs = coaching_prompt(item_meta, agg_item, agg_item.get("evidence") or agg_item.get("comments") or [])
    data = extract_json(generate_fn(msgs)) or {}
    return {
        "diagnosis": str(data.get("diagnosis", "")).strip(),
        "how_to": _as_lines(data.get("how_to")),          # 항상 줄 리스트
        "example_lines": _as_lines(data.get("example_lines")),
    }


# ── 리포트 조립 ────────────────────────────────────────────────────────────
def _bar(score: float) -> str:
    full = int(round(score))
    return "●" * full + "○" * (5 - full)


def build_coaching_report(rows: list[dict], *, instructor: str = "강사",
                          generate_fn=None, period: str = "", k_priority: int = 3,
                          k_strength: int = 3, log=print) -> str:
    """분석행 → 강사 코칭 리포트(markdown 문자열).

    generate_fn 이 None 이면 LLM 코칭 없이 집계·우선순위만(빠른 미리보기). 있으면 우선순위
    항목마다 구체 코칭을 붙인다.
    """
    agg = aggregate(rows)
    if not agg:
        return f"# {instructor} 코칭 리포트\n\n분석 데이터가 없습니다."
    cats = category_summary(agg)
    priorities = pick_priorities(agg, k_priority)
    strengths = pick_strengths(agg, k_strength)
    overall = round(mean(it["mean"] for it in agg.values()), 2)
    overall_trend = round(mean(it["trend"] for it in agg.values()), 2)
    n_sessions = len({(r["date"], r["session"]) for r in rows})

    L = []
    L.append(f"# 🎓 {instructor} 강의 코칭 리포트")
    if period:
        L.append(f"\n> 기간: {period} · {n_sessions}개 세션 분석")
    L.append(f"\n**종합 강의력 {overall}/5** (추이 {overall_trend:+}) · "
             f"항목 평균 5점 만점\n")

    # 카테고리 요약
    L.append("## 카테고리 요약\n")
    L.append("| 영역 | 점수 | |")
    L.append("|---|---|---|")
    for c in sorted(cats):
        s = cats[c]["score"]
        L.append(f"| {c} {cats[c]['name']} | {s:.1f} | {_bar(s)} |")

    # 강점
    L.append("\n## 💪 강점 (꾸준히 잘하는 점)\n")
    for s in strengths:
        L.append(f"- **{s['title']}** — 평균 {s['mean']}/5 (추이 {s['trend']:+}). "
                 f"{CATEGORIES.get(s['category'], '')} 영역.")

    # 개선 우선순위 + 코칭
    L.append("\n## 🎯 개선 우선순위 (중요도·점수 가중)\n")
    for i, p in enumerate(priorities, 1):
        L.append(f"### {i}. {p['title']}  ·  평균 {p['mean']}/5 (추이 {p['trend']:+}, "
                 f"가중치 {p['weight']})")
        L.append(f"\n{p.get('description','')}\n")
        # 근거
        ev = p.get("evidence") or p.get("comments") or []
        if ev:
            L.append("**실제 강의 근거(낮은 세션):**")
            for e in sorted(ev, key=lambda x: (x.get("score") or 9))[:3]:
                txt = e.get("quote") or e.get("comment", "")
                L.append(f"> [{e.get('date','')} {e.get('session','')} {e.get('score','')}점] {txt}")
            L.append("")
        # LLM 코칭
        if generate_fn is not None:
            log(f"  코칭 생성: {p['title']} (LLM)…")
            c = _coach_one(p, p, generate_fn)
            if c["diagnosis"]:
                L.append(f"**진단** — {c['diagnosis']}")
            if c["how_to"]:
                L.append("\n**개선 방법:**")
                for h in c["how_to"]:
                    L.append(f"- {h}")
            if c["example_lines"]:
                L.append("\n**바로 쓸 수 있는 멘트:**")
                for ln in c["example_lines"]:
                    L.append(f"- “{ln}”")
        L.append("")

    return "\n".join(L)


def to_payload(rows: list[dict], *, instructor: str = "강사", generate_fn=None,
               period: str = "") -> dict:
    """대시보드/JSON 소비용 구조화 산출(집계+우선순위+코칭)."""
    agg = aggregate(rows)
    priorities = pick_priorities(agg)
    if generate_fn is not None:
        for p in priorities:
            p["coaching"] = _coach_one(p, p, generate_fn)
    return {
        "instructor": instructor, "period": period,
        "category_summary": category_summary(agg),
        "strengths": pick_strengths(agg), "priorities": priorities,
    }
