"""실시간 부분점수 — 누적 발화로 '지금까지' 메트릭 항목(5개)을 잠정 채점.

전체 18항목 중 규칙 기반 5항목(반복·완결·일관·속도·복습)만 윈도우로 결정적 계산 가능 →
강의 진행 중 '부분 점수' 게이지로 보여준다. 나머지 holistic 13항목은 전체 통독 필요 →
강의 후 batch 에서 확정(여기선 미산출).

reuse: compute_metrics + score_metric_item (배치 채점과 동일 로직 — 잠정/최종 일관).
"""
from __future__ import annotations

from src.analyze.checklist import WEIGHT_VALUE, by_key
from src.analyze.metrics import compute_metrics, score_metric_item

# 실시간 채점 가능한 항목(hybrid METRIC_ITEMS 와 동일 — 규칙 기반).
LIVE_ITEMS = ["C1_repetition", "C1_completeness", "C1_consistency", "C4_pace", "C2_review"]


def _blocks(utterances: list[tuple[int, str]]) -> list[dict]:
    """(sec,text) → compute_metrics 가 받는 블록(텍스트+시간). end_sec=다음 발화 시작."""
    out = []
    for i, (sec, text) in enumerate(utterances):
        nxt = utterances[i + 1][0] if i + 1 < len(utterances) else sec
        out.append({"text": text, "start_sec": sec, "end_sec": max(nxt, sec)})
    return out


def live_partial_score(utterances: list[tuple[int, str]]) -> dict:
    """누적 발화 → 메트릭 5항목 잠정 점수 + 부분 종합(0~100).

    반환 {"items": {key:{score,comment}}, "partial_total": 0~100|None,
          "covered": n, "of": 18, "metrics": {...}}.
    """
    if len(utterances) < 2:
        return {"items": {}, "partial_total": None, "covered": 0, "of": 18, "metrics": {}}
    raw_texts = [t for _, t in utterances]
    metrics = compute_metrics(_blocks(utterances), raw_texts=raw_texts)
    meta = by_key()

    items, num, den = {}, 0.0, 0
    for key in LIVE_ITEMS:
        r = score_metric_item(key, metrics)
        sc = r.get("score")
        items[key] = {"title": meta.get(key, {}).get("title", key),
                      "score": sc, "comment": r.get("comment", "")}
        if isinstance(sc, (int, float)):
            w = WEIGHT_VALUE.get(meta.get(key, {}).get("weight", "mid"), 2)
            num += (sc / 5 * 100) * w
            den += w
    return {
        "items": items,
        "partial_total": round(num / den, 1) if den else None,
        "covered": sum(1 for v in items.values() if v["score"] is not None),
        "of": 18, "metrics": metrics,
    }


def gauge_bar(score: float, width: int = 20) -> str:
    """0~100 점수 → 텍스트 게이지 바."""
    if score is None:
        return "—" * width
    fill = int(round(score / 100 * width))
    return "█" * fill + "░" * (width - fill)
