"""라이브 넛지 시뮬 스모크 — 합성 발화로 규칙·쿨다운·윈도우 검증(외부데이터 없이).

사용: python -m scripts.smoke_live
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.live.nudge import (LiveConfig, Nudge, coalesce,  # noqa: E402
                            parse_transcript, simulate)


def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ✓ {msg}")


def test_filler_fires():
    print("· 필러 폭증 → 넛지 발화")
    # 0~200초, 매 10초 '이렇게' 도배 발화 → 필러율 매우 높음
    utt = [(s, "이렇게 이렇게 그래서 막 이제 이렇게 데이터를 봅니다") for s in range(0, 200, 10)]
    n = simulate(utt, LiveConfig(window_sec=120, min_words=30, cooldown_sec=60))
    rules = {x.rule for x in n}
    _check("filler" in rules, f"filler 넛지 발화됨 (rules={rules})")
    _check("dominant" in rules, "지배 필러('이렇게') 넛지 발화됨")


def test_clean_no_fire():
    print("· 깨끗한 발화 → 넛지 없음")
    utt = [(s, "데이터베이스 인덱스는 검색 성능을 높이는 자료구조입니다") for s in range(0, 200, 10)]
    n = simulate(utt, LiveConfig(window_sec=120, min_words=30, check_silence_sec=10**9,
                                 objective_grace_sec=10**9))
    _check([x for x in n if x.rule in ("filler", "dominant", "pace")] == [],
           "필러·속도 넛지 없음(클린 발화)")


def test_cooldown():
    print("· 쿨다운 — 동일 규칙 연속 억제")
    utt = [(s, "이렇게 이렇게 막 이제 그래서 이렇게") for s in range(0, 600, 5)]
    n = simulate(utt, LiveConfig(window_sec=120, min_words=20, cooldown_sec=120))
    fillers = [x for x in n if x.rule == "filler"]
    secs = [x.sec for x in fillers]
    gaps_ok = all(secs[i+1] - secs[i] >= 120 for i in range(len(secs)-1))
    _check(gaps_ok, f"filler 넛지 간격 ≥쿨다운(120s) (secs={secs})")


def test_objective_and_silence():
    print("· 학습목표 미안내 + 이해확인 침묵")
    # 목표 키워드 없이, 이해확인 cue 없이 길게
    utt = [(s, "인덱스는 비트리 구조이고 리프 노드에 데이터가 정렬됩니다") for s in range(0, 900, 30)]
    n = simulate(utt, LiveConfig(objective_grace_sec=300, check_silence_sec=600))
    rules = {x.rule for x in n}
    _check("objective" in rules, "도입 목표 미안내 넛지(1회)")
    _check("check_silence" in rules, "이해확인 장기 침묵 넛지")
    obj = [x for x in n if x.rule == "objective"]
    _check(len(obj) == 1, f"objective 는 1회만 (got {len(obj)})")


def test_parse():
    print("· transcript 파싱(시작 0초 정규화)")
    txt = "<09:00:10> 00000000: 안녕하세요\n<09:00:20> 00000000: 시작합니다\n잡줄\n"
    u = parse_transcript(txt)
    _check(u == [(0, "안녕하세요"), (10, "시작합니다")], f"파싱·정규화 정확 (got {u})")


def test_coalesce():
    print("· digest 병합 — 우선순위·최소간격")
    ns = [Nudge(10, "filler", "warn", "f", 0.1),
          Nudge(15, "dominant", "warn", "d", 0.2),    # 10s 클러스터, 우선순위 dominant>filler
          Nudge(200, "check_silence", "info", "c", 0)]
    out = coalesce(ns, min_gap_sec=150, cluster_sec=30)
    _check(len(out) == 2, f"클러스터 병합 → 2건 (got {len(out)})")
    _check(out[0].rule == "dominant", "근접 클러스터에서 우선순위 높은 dominant 선택")
    _check(out[1].sec - out[0].sec >= 150, "최소간격 보장")
    # 최소간격 미만 저우선 넛지는 생략
    ns2 = [Nudge(10, "dominant", "warn", "d", 0.2), Nudge(60, "filler", "warn", "f", 0.1)]
    _check(len(coalesce(ns2, min_gap_sec=150, cluster_sec=30)) == 1, "간격 미달 후속 생략")


def main():
    print("라이브 넛지 시뮬 스모크\n")
    test_filler_fires()
    test_clean_no_fire()
    test_cooldown()
    test_objective_and_silence()
    test_parse()
    test_coalesce()
    print("\n✅ 전부 통과 — 규칙·쿨다운·윈도우·파싱 정상.")


if __name__ == "__main__":
    main()
