"""지표 선계산(§⑥ 🔵 metric · 🔴 global 보조) — merged 블록에서 결정적으로 계산.

LLM 전에 숫자부터: 발화속도(pace)·필러율(filler)은 타임스탬프·원문에서 규칙으로 산출,
LLM 은 해석/코멘트만(또는 규칙 채점). 전역 항목(언어일관성·완결성)도 여기 신호를 쓴다.

⚠️ 필러율은 **정제 전 원문(merged.text)** 에서 측정한다 — 정제(④)가 군더더기를 이미
지웠으므로 clean_text 로 재면 0에 가깝다.
"""
from __future__ import annotations

import re

from src import config
from src.preprocess.merge import is_incomplete

# 존댓말/반말 — **정제 clean_text 의 문장(부호로 구분) 끝 어미**로 판정(신뢰 가능).
# 존댓말 검사(니다/요…)를 먼저 — '합니다'는 '다'로도 끝나므로 반말보다 우선 판정.
_SENT_SPLIT = re.compile(r"[.!?]+|\n")
_HON_END = re.compile(r"(니다|세요|십시오|[어아에예]요|[나까네지구군]요|잖아요|거든요|예요|요)$")
_CAS_END = re.compile(r"(다|어|아|지|네|군|거든|잖아|야|까|래|단다)$")


def _words(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]+", text)


def compute_metrics(blocks: list[dict], clean_text: str = "") -> dict:
    """한 강의의 merged 블록(raw) + 정제 clean_text → 지표 dict.

    filler·pace 는 raw(merged) 기준(정제가 군더더기를 지웠으므로). 존댓말 일관성은
    문장부호가 있는 clean_text 기준(merged 는 문장중간 끊김). clean_text 없으면 0.
    반환: {pace_cpm, pace_wpm, filler_rate, honorific_ratio, incomplete_ratio,
           n_blocks, n_chars, elapsed_min}
    """
    if not blocks:
        return {}
    text = " ".join(b.get("text", "") for b in blocks)
    n_chars = len(text)
    words = _words(text)
    n_words = len(words)

    # 경과 시간(분) — 첫 시작 ~ 마지막 끝
    start = min(b["start_sec"] for b in blocks)
    end = max(b["end_sec"] for b in blocks)
    elapsed_min = max((end - start) / 60.0, 1e-6)

    # 발화 속도
    pace_cpm = n_chars / elapsed_min      # 분당 글자수
    pace_wpm = n_words / elapsed_min      # 분당 어절수

    # 필러율(원문 기준) — **토큰 단위** 매칭(substring 아님). '요/네/음' 같은 1글자
    # 필러를 text.count 로 세면 어미의 '요' 까지 잡혀 폭증 → 어절(token) 일치로 카운트.
    filler_set = set(config.FILLER_WORDS)
    filler_n = sum(1 for w in words if w in filler_set)
    filler_rate = filler_n / max(n_words, 1)

    # 존댓말/반말 비율 — 정제 clean_text 문장 끝 어미 기준(신뢰 가능)
    hon = cas = 0
    for s in _SENT_SPLIT.split(clean_text or ""):
        s = s.strip()
        if not s:
            continue
        if _HON_END.search(s):       # 존댓말 우선(합니다는 다로도 끝남)
            hon += 1
        elif _CAS_END.search(s):
            cas += 1
    honorific_ratio = round(hon / max(hon + cas, 1), 3) if (hon + cas) else None

    # 미완결 문장 비율 — 완결성 신호(블록 끝이 접속어미)
    incomplete_n = sum(1 for b in blocks if is_incomplete(b.get("text", "")))
    incomplete_ratio = incomplete_n / max(len(blocks), 1)

    return {
        "pace_cpm": round(pace_cpm, 1),
        "pace_wpm": round(pace_wpm, 1),
        "filler_rate": round(filler_rate, 4),
        "filler_n": filler_n,
        "honorific_ratio": honorific_ratio,
        "incomplete_ratio": round(incomplete_ratio, 3),
        "n_blocks": len(blocks),
        "n_chars": n_chars,
        "elapsed_min": round(elapsed_min, 1),
    }


def score_metric_item(item_key: str, metrics: dict) -> dict:
    """🔵 지표형 항목 → 규칙 채점(1~5) + 수치 evidence. (임계값 §2차 EDA 캘리브레이션 전 잠정)

    반환: {"score", "value", "comment"}
    """
    if item_key == "C3_pace":          # 발화 속도 적절성
        cpm = metrics.get("pace_cpm", 0)
        lo, hi = config.PACE_CPM_LOW, config.PACE_CPM_HIGH
        if lo <= cpm <= hi:
            score, note = 5, "적절"
        elif cpm < lo:
            score, note = 3, "다소 느림"
        else:
            score, note = 2, "다소 빠름(수강생 따라가기 부담 가능)"
        return {"score": score, "value": {"name": "pace_cpm", "value": cpm},
                "comment": f"분당 {cpm}자 — {note} (잠정 기준 {lo}~{hi}, §2차 EDA 보정 예정)"}

    if item_key == "C1_repetition":    # 불필요한 반복(필러)
        rate = metrics.get("filler_rate", 0)
        hi = config.FILLER_RATE_HIGH
        if rate <= hi * 0.5:
            score, note = 5, "필러 적음"
        elif rate <= hi:
            score, note = 3, "보통"
        else:
            score, note = 2, "필러·반복 잦음"
        return {"score": score, "value": {"name": "filler_rate", "value": rate},
                "comment": f"필러율 {rate} ({metrics.get('filler_n')}회) — {note} "
                           f"(잠정 기준 {hi}, §2차 EDA 보정 예정)"}

    return {"score": None, "value": None, "comment": "지표 미정의"}
