"""지표 선계산(§⑥ 🔵 metric · 🔴 global 보조) — merged 블록에서 결정적으로 계산.

LLM 전에 숫자부터: 발화속도(pace)·필러율(filler)은 타임스탬프·원문에서 규칙으로 산출,
LLM 은 해석/코멘트만(또는 규칙 채점). 전역 항목(언어일관성·완결성)도 여기 신호를 쓴다.

⚠️ C1 언어표현 신호(필러·존댓말 일관성)는 모두 **정제 전 원문(merged.text)** 에서
측정한다 — 정제(④)가 군더더기·반말을 이미 지워 clean_text 로 재면 "깨끗함=만점"으로
속는다(gold 검증: clean 존댓말비율 1.0 vs raw 0.53). docs/고도화/01 §7 참조.
"""
from __future__ import annotations

import re
from collections import Counter

from src import config
from src.preprocess.merge import is_incomplete

# 존댓말/반말 — **원문(merged.text) 의 문장(부호로 구분) 끝 어미**로 판정.
# 존댓말 검사(니다/요…)를 먼저 — '합니다'는 '다'로도 끝나므로 반말보다 우선 판정.
_SENT_SPLIT = re.compile(r"[.!?]+|\n")
_HON_END = re.compile(r"(니다|세요|십시오|[어아에예]요|[나까네지구군]요|잖아요|거든요|예요|요)$")
_CAS_END = re.compile(r"(다|어|아|지|네|군|거든|잖아|야|까|래|단다)$")


def _words(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]+", text)


def compute_metrics(blocks: list[dict], clean_text: str = "",
                    raw_texts: list[str] = None) -> dict:
    """한 강의의 merged 블록(raw) → C1 언어표현 지표 dict.

    필러·존댓말 일관성·완결성 모두 raw(merged.text) 기준 — 정제본은 결함을 지워 못 잰다.
    raw_texts(정제 전 **발화 단위**, raw.jsonl) 가 주어지면 완결성을 발화 단위로 측정한다
    — merged 블록은 gap 으로 합쳐져 끊김을 뭉개므로(gold 검증) 발화 단위가 더 정확.
    (clean_text 인자는 하위호환용으로 남기되 사용하지 않는다.)
    반환: {... incomplete_ratio, incomplete_ratio_utt, ...}
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
    filler_counts = Counter(w for w in words if w in filler_set)
    filler_n = sum(filler_counts.values())
    filler_rate = filler_n / max(n_words, 1)
    # 지배 필러 — 가장 많이 반복된 단일 필러의 비중('특정 표현 과반복' 신호, 예: '이렇게')
    top_filler, top_n = (filler_counts.most_common(1)[0] if filler_counts else (None, 0))
    max_filler_rate = top_n / max(n_words, 1)

    # 존댓말/반말 비율 — **원문(raw) 문장 끝 어미** 기준(정제본은 존댓말로 정규화돼 무의미)
    hon = cas = 0
    for s in _SENT_SPLIT.split(text):
        s = s.strip()
        if not s:
            continue
        if _HON_END.search(s):       # 존댓말 우선(합니다는 다로도 끝남)
            hon += 1
        elif _CAS_END.search(s):
            cas += 1
    honorific_ratio = round(hon / max(hon + cas, 1), 3) if (hon + cas) else None

    # 미완결 문장 비율 — 완결성 신호(끝이 접속어미). merged 블록 기준(하위호환).
    incomplete_n = sum(1 for b in blocks if is_incomplete(b.get("text", "")))
    incomplete_ratio = incomplete_n / max(len(blocks), 1)
    # 발화 단위(raw.jsonl) — merged 는 끊김을 뭉개므로 발화 단위가 사람 판단에 더 부합(§완결성).
    incomplete_ratio_utt = None
    if raw_texts:
        inc_u = sum(1 for t in raw_texts if is_incomplete(t or ""))
        incomplete_ratio_utt = round(inc_u / max(len(raw_texts), 1), 3)

    # C5 상호작용 cue(raw 기준 — refine 가 지우는 구어체 신호). 10분당 빈도.
    check_cue_n = sum(text.count(c) for c in config.C5_CHECK_CUES)
    engage_cue_n = sum(text.count(c) for c in config.C5_ENGAGE_CUES)
    check_per10 = check_cue_n / elapsed_min * 10
    engage_per10 = engage_cue_n / elapsed_min * 10

    return {
        "pace_cpm": round(pace_cpm, 1),
        "pace_wpm": round(pace_wpm, 1),
        "filler_rate": round(filler_rate, 4),
        "filler_n": filler_n,
        "max_filler_rate": round(max_filler_rate, 4),
        "top_filler": top_filler,
        "honorific_ratio": honorific_ratio,
        "incomplete_ratio": round(incomplete_ratio, 3),
        "incomplete_ratio_utt": incomplete_ratio_utt,
        "check_cue_n": check_cue_n,
        "engage_cue_n": engage_cue_n,
        "check_per10": round(check_per10, 2),
        "engage_per10": round(engage_per10, 2),
        "n_blocks": len(blocks),
        "n_chars": n_chars,
        "elapsed_min": round(elapsed_min, 1),
    }


def _band(rate: float, lo: float, mid: float, hi: float) -> int:
    """10분당 빈도 → 1~5. 0=없음(1) · <lo 미흡(2) · [lo,mid] 보통(3) · (mid,hi] 자주(4) · >hi(5)."""
    if rate <= 0:
        return 1
    if rate < lo:
        return 2
    if rate <= mid:
        return 3
    if rate <= hi:
        return 4
    return 5


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

    if item_key == "C1_repetition":    # 불필요한 반복(필러·특정표현 과반복)
        rate = metrics.get("filler_rate", 0)
        mx = metrics.get("max_filler_rate", 0)
        top = metrics.get("top_filler")
        hi, dom = config.FILLER_RATE_HIGH, config.FILLER_DOMINANT_HIGH
        # 총 필러율 OR 지배 필러 둘 중 하나만 넘어도 '잦음' — 항목이 '특정 표현 과반복'을 봄
        if rate > hi or mx > dom:
            score, note = 2, f"필러·반복 잦음(최다 '{top}' {mx:.1%})"
        elif rate > hi * 0.5:
            score, note = 3, "보통"
        else:
            score, note = 5, "필러 적음"
        return {"score": score, "value": {"name": "filler_rate", "value": rate,
                                          "max_filler_rate": mx, "top_filler": top},
                "comment": f"필러율 {rate} ({metrics.get('filler_n')}회), 최다 '{top}' "
                           f"{metrics.get('max_filler_rate')} — {note} "
                           f"(기준 율>{hi}|지배>{dom}, §2차 보정 대상)"}

    if item_key == "C5_check":         # 이해 확인 질문 — raw cue 빈도(refine 가 지움)
        r, n = metrics.get("check_per10", 0), metrics.get("check_cue_n", 0)
        score = _band(r, *config.C5_CHECK_PER10)
        return {"score": score, "value": {"name": "check_per10", "value": r, "n": n},
                "comment": f"이해확인 표현 {n}회 ({r}/10분) — raw 기준 "
                           f"(되셨어요·이해가죠·맞죠 등, gold 보정 잠정)"}

    if item_key == "C5_engage":        # 참여 유도 — raw cue 빈도(refine 가 지움)
        r, n = metrics.get("engage_per10", 0), metrics.get("engage_cue_n", 0)
        score = _band(r, *config.C5_ENGAGE_PER10)
        return {"score": score, "value": {"name": "engage_per10", "value": r, "n": n},
                "comment": f"참여유도 표현 {n}회 ({r}/10분) — raw 기준 "
                           f"(해보세요·같이·풀어보 등, gold 보정 잠정)"}

    return {"score": None, "value": None, "comment": "지표 미정의"}


def score_global_metric_item(item_key: str, metrics: dict) -> dict | None:
    """🔴 global 항목 중 지표로 직접 채점 가능한 것을 규칙 점수화(1~5).

    C1_consistency(언어 일관성), C1_completeness(발화 완결성)는 honorific_ratio /
    incomplete_ratio 라는 결정적 신호가 있어, LLM 판단의 닻(anchor)으로 쓸 수 있다.
    engine 의 global 평가에서 이 점수를 참고값으로 프롬프트에 넣거나, LLM 점수와
    혼합(예: 평균)해 전역 항목 점수를 안정화한다.

    지표가 없으면(예: 블록 부재로 honorific_ratio=None) None 을 반환해
    호출부가 LLM 단독 평가로 fallback 하게 한다.

    반환: {"score", "value", "comment"} 또는 None
    """
    if item_key == "C1_consistency":          # 언어 일관성 (존댓말 비율)
        hr = metrics.get("honorific_ratio")
        if hr is None:
            return None
        if hr >= 0.9:
            score, note = 5, "대체로 일관"
        elif hr >= 0.7:
            score, note = 3, "다소 혼용"
        else:
            score, note = 2, "비일관(존댓말/반말 혼용 잦음)"
        return {"score": score, "value": {"name": "honorific_ratio", "value": hr},
                "comment": f"존댓말 비율 {hr} — {note} (1.0=완전 일관)"}

    if item_key == "C1_completeness":         # 발화 완결성 (미완결 비율)
        # 발화 단위(raw.jsonl)가 있으면 우선 — merged 블록은 끊김을 뭉개 과대평가(gold: 둘 다 5→실제 3).
        iu = metrics.get("incomplete_ratio_utt")
        if iu is not None:
            # gold(02-02 0.084·02-06 0.099 = 둘 다 3) 보정. 발화단위 분포 0.084~0.119.
            if iu < 0.06:
                score, note = 5, "문장 완결성 우수"
            elif iu < 0.08:
                score, note = 4, "양호"
            elif iu < 0.115:
                score, note = 3, "보통(일부 미완결)"
            else:
                score, note = 2, "미완결 잦음"
            return {"score": score, "value": {"name": "incomplete_ratio_utt", "value": iu},
                    "comment": f"발화 미완결 비율 {iu} — {note} (발화 단위, 낮을수록 완결)"}
        ir = metrics.get("incomplete_ratio")    # 폴백: merged 블록 단위(구 기준)
        if ir is None:
            return None
        if ir < 0.1:
            score, note = 5, "문장 완결성 우수"
        elif ir < 0.25:
            score, note = 4, "양호"
        else:
            score, note = 2, "미완결 문장 잦음"
        return {"score": score, "value": {"name": "incomplete_ratio", "value": ir},
                "comment": f"미완결 문장 비율 {ir} — {note} (블록 단위)"}

    return None
