"""강의력 점수 ↔ 수강생 피드백 상관분석.

세션 단위로 (강의력 18항목·5카테고리) 와 (만족도·이해도·추천율) 을 정렬해, 어떤 강의력
항목이 만족도와 가장 연관되는지 Pearson/Spearman 상관으로 뽑는다. scipy 없이 numpy 로 구현.
"""
from __future__ import annotations

import numpy as np

from src.analyze.checklist import CATEGORIES, by_key
from src.scoring.scoring import score_lecture

_SESSION_ORDER = {"오전": 0, "오후": 1, "종일": 0}


# ── 상관 계수(numpy, scipy 불필요) ────────────────────────────────────────
def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _rank(a: np.ndarray) -> np.ndarray:
    """평균 순위(동점 처리) — Spearman 용."""
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(len(a), dtype=float)
    # 동점 평균 처리
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inv, ranks)
    return (sums / counts)[inv]


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    return _pearson(_rank(x), _rank(y))


# ── 세션 테이블 구성 ───────────────────────────────────────────────────────
def session_table(score_rows: list[dict], feedback: list[dict]) -> dict:
    """세션 교집합으로 정렬된 {item/category 점수} + {피드백 평균} 배열 묶음.

    반환 {"sessions":[(date,session)], "items":{key:np.array}, "cats":{c:np.array},
          "satisfaction":np.array, "understanding":np.array, "recommend":np.array}.
    """
    # 강의력: 세션별 item 점수 + 카테고리 점수
    by_sess_rows: dict = {}
    for r in score_rows:
        by_sess_rows.setdefault((r["date"], r["session"]), []).append(r)
    item_scores: dict = {}
    cat_scores: dict = {}
    for sk, rows in by_sess_rows.items():
        sl = score_lecture(rows)
        cat_scores[sk] = sl.get("category_scores", {})
        item_scores[sk] = {r["item_key"]: r.get("score") for r in rows}

    # 피드백: 세션별 평균
    fb_agg: dict = {}
    for f in feedback:
        sk = (f["date"], f["session"])
        d = fb_agg.setdefault(sk, {"sat": [], "und": [], "rec": []})
        d["sat"].append(f["satisfaction"])
        d["und"].append(f["understanding"])
        d["rec"].append(f["recommend"])

    sessions = sorted(set(item_scores) & set(fb_agg),
                      key=lambda sk: (sk[0], _SESSION_ORDER.get(sk[1], 0)))
    meta = by_key()
    keys = list(meta)
    items = {k: np.array([item_scores[s].get(k, np.nan) for s in sessions], float) for k in keys}
    cats = {c: np.array([cat_scores[s].get(c, np.nan) for s in sessions], float) for c in CATEGORIES}
    sat = np.array([np.mean(fb_agg[s]["sat"]) for s in sessions], float)
    und = np.array([np.mean(fb_agg[s]["und"]) for s in sessions], float)
    rec = np.array([np.mean(fb_agg[s]["rec"]) for s in sessions], float)
    return {"sessions": sessions, "items": items, "cats": cats,
            "satisfaction": sat, "understanding": und, "recommend": rec,
            "n_feedback": sum(len(fb_agg[s]["sat"]) for s in sessions)}


def _drop_nan(x: np.ndarray, y: np.ndarray):
    m = ~(np.isnan(x) | np.isnan(y))
    return x[m], y[m]


def correlations(table: dict, target: str = "satisfaction") -> list[dict]:
    """각 강의력 항목 vs target(만족도/이해도) 상관. |pearson| 내림차순."""
    y = table[target]
    meta = by_key()
    out = []
    for k, x in table["items"].items():
        xx, yy = _drop_nan(x, y)
        m = meta.get(k, {})
        out.append({"key": k, "title": m.get("title", k), "category": m.get("category", ""),
                    "weight": m.get("weight", ""), "mean": round(float(np.nanmean(x)), 2),
                    "pearson": round(_pearson(xx, yy), 3), "spearman": round(_spearman(xx, yy), 3),
                    "n": int(len(xx))})
    out.sort(key=lambda d: (-(abs(d["pearson"]) if d["pearson"] == d["pearson"] else -1)))
    return out


def category_correlations(table: dict, target: str = "satisfaction") -> list[dict]:
    y = table[target]
    out = []
    for c, x in table["cats"].items():
        xx, yy = _drop_nan(x, y)
        out.append({"category": c, "name": CATEGORIES.get(c, c),
                    "mean": round(float(np.nanmean(x)), 2),
                    "pearson": round(_pearson(xx, yy), 3), "n": int(len(xx))})
    out.sort(key=lambda d: -(abs(d["pearson"]) if d["pearson"] == d["pearson"] else -1))
    return out


# ── 리포트 ─────────────────────────────────────────────────────────────────
def build_report(score_rows: list[dict], feedback: list[dict], *,
                 instructor: str = "강사", synthetic: bool = True) -> str:
    table = session_table(score_rows, feedback)
    n_sess = len(table["sessions"])
    if n_sess < 3:
        return "# 피드백 상관분석\n\n세션이 3개 미만이라 상관을 낼 수 없습니다."

    item_corr = correlations(table, "satisfaction")
    cat_corr = category_correlations(table, "satisfaction")
    und_corr = correlations(table, "understanding")[:5]
    avg_sat = round(float(np.mean(table["satisfaction"])), 2)
    avg_rec = round(float(np.mean(table["recommend"])) * 100, 1)

    L = [f"# 📊 {instructor} 강의력 ↔ 수강생 피드백 상관분석"]
    if synthetic:
        L.append("\n> ⚠️ **합성 샘플 데이터** — 실제 수강생 피드백이 없어, 일부 강의력 항목을 "
                 "만족도 동인으로 두고 잡음을 더해 생성했습니다. 아래 상관은 **분석 방법의 동작**을 "
                 "보이기 위한 것이며 실제 수강생 행동을 의미하지 않습니다.")
    L.append(f"\n- 분석 세션: **{n_sess}개** · 피드백 응답: **{table['n_feedback']}건**")
    L.append(f"- 평균 만족도: **{avg_sat}/5** · 추천율: **{avg_rec}%**\n")

    L.append("## 🔑 만족도와 가장 연관된 강의력 항목 (Top 8)\n")
    L.append("| 항목 | 카테고리 | 평균점수 | Pearson r | Spearman ρ |")
    L.append("|---|---|---|---|---|")
    for d in item_corr[:8]:
        L.append(f"| {d['title']} | {d['category']} | {d['mean']} | "
                 f"**{d['pearson']:+.2f}** | {d['spearman']:+.2f} |")

    L.append("\n## 카테고리별 상관 (만족도)\n")
    L.append("| 영역 | 평균 | Pearson r |")
    L.append("|---|---|---|")
    for d in cat_corr:
        L.append(f"| {d['category']} {d['name']} | {d['mean']} | {d['pearson']:+.2f} |")

    L.append("\n## 🧠 이해도와 가장 연관된 항목 (Top 5)\n")
    for d in und_corr:
        L.append(f"- **{d['title']}** ({d['category']}) — r={d['pearson']:+.2f}")

    # 인사이트
    top = item_corr[0]
    L.append("\n## 인사이트\n")
    L.append(f"- 만족도와 가장 강하게 연관된 항목은 **{top['title']}**(r={top['pearson']:+.2f}) "
             "입니다. 이 항목을 끌어올리면 만족도 개선 여지가 큽니다.")
    strong = [d['title'] for d in item_corr[:3] if d['pearson'] == d['pearson'] and d['pearson'] > 0]
    if strong:
        L.append(f"- 상위 연관 항목: {', '.join(strong)} → 코칭 우선순위와 교차 검토 권장.")
    return "\n".join(L)
