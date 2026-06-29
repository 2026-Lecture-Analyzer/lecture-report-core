"""실시간 넛지 엔진 — 발화 스트림을 받아 롤링 윈도우 메트릭으로 넛지를 발화.

순수·결정적(테스트 용이): simulate(utterances)는 동일 입력에 동일 타임라인을 낸다.
스트리밍 연동 시에도 같은 _Engine.feed(utterance) 를 발화 도착마다 호출하면 된다.
"""
from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass, field

from src import config
from src.preprocess.loader import parse_line

_FILLER_SET = set(config.FILLER_WORDS)

# 학습목표/도입 안내 신호(휴리스틱 키워드) — 도입부에 이게 없으면 넛지.
_OBJECTIVE_KW = ["오늘", "배울", "배워", "목표", "해볼", "할 거", "할거", "진행", "수업은", "강의는"]


@dataclass(frozen=True)
class Nudge:
    sec: int                 # 강의 경과 기준 초(발화 시각)
    rule: str
    severity: str            # "info" | "warn"
    message: str
    value: float = 0.0


@dataclass
class LiveConfig:
    window_sec: int = 180            # 롤링 윈도우(필러·속도·cue 계산 구간)
    min_words: int = 50             # 윈도우 표본이 이만큼 차야 메트릭 평가(초반 노이즈 방지)
    cooldown_sec: int = 120         # 동일 규칙 재발화 최소 간격
    objective_grace_sec: int = 300  # 도입 이 시간 내 학습목표 신호 없으면 1회 넛지
    check_silence_sec: int = 600    # 이해확인 cue 가 이만큼 없으면 넛지
    pace_high: float = None         # None=config.PACE_CPM_HIGH
    filler_high: float = None       # None=config.FILLER_RATE_HIGH
    dominant_high: float = None     # None=config.FILLER_DOMINANT_HIGH


def _signals(window: deque, span_sec: float, cfg: LiveConfig) -> dict:
    """윈도우 내 발화들로 필러·속도·cue 신호 계산."""
    texts = [t for _, t in window]
    joined = " ".join(texts)
    words = joined.split()
    n_words = len(words)
    fillers = Counter(w for w in words if w in _FILLER_SET)
    filler_n = sum(fillers.values())
    top_filler, top_n = (fillers.most_common(1)[0] if fillers else (None, 0))
    n_chars = sum(len(t) for t in texts)
    span_min = max(span_sec, 1) / 60
    check_n = sum(joined.count(c) for c in config.C5_CHECK_CUES)
    engage_n = (sum(joined.count(c) for c in config.C5_ENGAGE_CUES)
                + len(re.findall(config.C5_ENGAGE_GACHI, joined)))
    return {
        "n_words": n_words,
        "filler_rate": filler_n / n_words if n_words else 0.0,
        "max_filler_rate": top_n / n_words if n_words else 0.0,
        "top_filler": top_filler,
        "pace_cpm": n_chars / span_min if span_min else 0.0,
        "check_n": check_n, "engage_n": engage_n,
    }


class _Engine:
    """발화 도착마다 feed() → 발화할 넛지 리스트 반환. 스트리밍/시뮬 공용."""

    def __init__(self, cfg: LiveConfig):
        self.cfg = cfg
        self.win: deque = deque()
        self.last_fired: dict[str, int] = {}
        self.last_check_sec = 0
        self.objective_seen = False
        self.objective_fired = False
        self.pace_high = cfg.pace_high or config.PACE_CPM_HIGH
        self.filler_high = cfg.filler_high or config.FILLER_RATE_HIGH
        self.dominant_high = cfg.dominant_high or config.FILLER_DOMINANT_HIGH

    def _cooled(self, rule: str, now: int) -> bool:
        return now - self.last_fired.get(rule, -10**9) >= self.cfg.cooldown_sec

    def _fire(self, out: list, n: Nudge):
        self.last_fired[n.rule] = n.sec
        out.append(n)

    def feed(self, sec: int, text: str) -> list[Nudge]:
        cfg = self.cfg
        out: list[Nudge] = []
        # 윈도우 갱신
        self.win.append((sec, text))
        while self.win and sec - self.win[0][0] > cfg.window_sec:
            self.win.popleft()
        # cue/목표 추적
        if any(c in text for c in config.C5_CHECK_CUES):
            self.last_check_sec = sec
        if sec <= cfg.objective_grace_sec and any(k in text for k in _OBJECTIVE_KW):
            self.objective_seen = True

        span = sec - self.win[0][0] if self.win else 0
        sig = _signals(self.win, span, cfg)

        # 규칙 평가(표본 충분 + 쿨다운)
        if sig["n_words"] >= cfg.min_words:
            if sig["filler_rate"] > self.filler_high and self._cooled("filler", sec):
                self._fire(out, Nudge(sec, "filler", "warn",
                    f"필러 과다 — 최근 {cfg.window_sec//60}분 필러율 {sig['filler_rate']:.1%}",
                    round(sig["filler_rate"], 4)))
            if (sig["max_filler_rate"] > self.dominant_high and sig["top_filler"]
                    and self._cooled("dominant", sec)):
                self._fire(out, Nudge(sec, "dominant", "warn",
                    f"'{sig['top_filler']}' 반복 — 최근 비중 {sig['max_filler_rate']:.1%}",
                    round(sig["max_filler_rate"], 4)))
            if sig["pace_cpm"] > self.pace_high and self._cooled("pace", sec):
                self._fire(out, Nudge(sec, "pace", "warn",
                    f"말이 빠름 — {sig['pace_cpm']:.0f}자/분 (권장 ≤{int(self.pace_high)})",
                    round(sig["pace_cpm"], 1)))

        # 이해확인 cue 장기 부재
        if (sec - self.last_check_sec > cfg.check_silence_sec and self._cooled("check_silence", sec)):
            self._fire(out, Nudge(sec, "check_silence", "info",
                f"{(sec - self.last_check_sec)//60}분째 이해확인 질문 없음 — '여기까지 이해되셨어요?'",
                sec - self.last_check_sec))

        # 도입부 학습목표 미안내(1회)
        if (not self.objective_fired and sec >= cfg.objective_grace_sec
                and not self.objective_seen):
            self.objective_fired = True
            self._fire(out, Nudge(sec, "objective", "info",
                f"도입 {cfg.objective_grace_sec//60}분간 학습목표/진행순서 안내 신호가 약함",
                sec))
        return out


def parse_transcript(text: str) -> list[tuple[int, str]]:
    """transcript txt → [(sec_of_day, text)] (강사 발화만, 시간 오름차순)."""
    out = []
    for line in text.splitlines():
        p = parse_line(line)
        if not p:
            continue
        hh, mm, ss, _spk, utt = p
        out.append((hh * 3600 + mm * 60 + ss, utt))
    out.sort(key=lambda x: x[0])
    if out:                                  # 강의 시작=0초로 정규화
        base = out[0][0]
        out = [(s - base, t) for s, t in out]
    return out


def simulate(utterances: list[tuple[int, str]], cfg: LiveConfig = None) -> list[Nudge]:
    """발화 스트림 리플레이 → 발화됐을 넛지 타임라인."""
    cfg = cfg or LiveConfig()
    eng = _Engine(cfg)
    fired: list[Nudge] = []
    for sec, text in utterances:
        fired.extend(eng.feed(sec, text))
    return fired


# ── 우선순위 병합(digest) — 넛지 피로 억제 ────────────────────────────────
# 강사 화면엔 '지금 가장 중요한 1건'만. 클수록 우선. 동률이면 임계 초과폭(value)으로.
RULE_PRIORITY = {
    "objective": 5,       # 도입 1회 — 놓치면 강의 전체 영향
    "pace": 4,            # 즉시 교정 가능·체감 큼
    "dominant": 3,        # 특정 필러 도배(가장 거슬림)
    "filler": 2,
    "check_silence": 1,   # 부드러운 상시 리마인더
}


class OnlineGate:
    """스트리밍용 온라인 병합 — 도착 순서대로 offer()하면 발화할 넛지를 즉시 돌려준다.

    coalesce 의 온라인 버전: 근접(cluster_sec) 넛지는 버퍼에 모았다가, 그 창이 지나면 우선순위
    최고 1건만 flush(전역 min_gap 보장). 강의 진행 중 '지금 띄울 1건'을 결정한다.
    """

    def __init__(self, *, min_gap_sec: int = 150, cluster_sec: int = 30, priority: dict = None):
        self.min_gap = min_gap_sec
        self.cluster = cluster_sec
        self.pri = priority or RULE_PRIORITY
        self.last_emit = -10**9
        self.buf: list[Nudge] = []

    def _flush(self) -> list[Nudge]:
        if not self.buf:
            return []
        best = max(self.buf, key=lambda n: (self.pri.get(n.rule, 0), n.value))
        self.buf = []
        if best.sec - self.last_emit >= self.min_gap:
            self.last_emit = best.sec
            return [best]
        return []

    def offer(self, n: Nudge) -> list[Nudge]:
        emitted: list[Nudge] = []
        if self.buf and n.sec - self.buf[0].sec > self.cluster:
            emitted += self._flush()
        self.buf.append(n)
        return emitted

    def close(self) -> list[Nudge]:
        return self._flush()


def coalesce(nudges: list[Nudge], *, min_gap_sec: int = 150, cluster_sec: int = 30,
             priority: dict = None) -> list[Nudge]:
    """난사된 넛지 → '한 번에 1건' 희소 스트림.

    ① 근접(cluster_sec 내) 넛지는 우선순위 최고 1건으로 병합 → ② 전역 최소간격(min_gap_sec)
    미만이면 생략. 결과적으로 강사는 ~min_gap 마다 가장 중요한 신호 하나만 본다.
    """
    pri = priority or RULE_PRIORITY
    ns = sorted(nudges, key=lambda n: n.sec)
    out: list[Nudge] = []
    last = -10**9
    i = 0
    while i < len(ns):
        base = ns[i].sec
        j = i
        while j < len(ns) and ns[j].sec - base <= cluster_sec:
            j += 1
        best = max(ns[i:j], key=lambda n: (pri.get(n.rule, 0), n.value))
        if best.sec - last >= min_gap_sec:
            out.append(best)
            last = best.sec
        i = j
    return out
