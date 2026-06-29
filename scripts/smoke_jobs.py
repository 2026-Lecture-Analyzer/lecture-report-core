"""워커풀 + 전역 거버너 스모크 — LLM 없이 동시성·큐·호출상한 검증.

사용: python -m scripts.smoke_jobs
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.governor import BudgetExceeded, RateGovernor  # noqa: E402


def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ✓ {msg}")


def test_governor_budget():
    print("· 거버너 총 예산")
    g = RateGovernor(total_budget=3)
    f = g.wrap(lambda: "ok")
    _check(f() == "ok" and f() == "ok" and f() == "ok", "예산 내 3회 통과")
    try:
        f()
        _check(False, "4회째 BudgetExceeded")
    except BudgetExceeded:
        _check(True, "4회째 BudgetExceeded 발생")
    _check(g.stats()["used"] == 3, "used=3 (거부된 4회째는 예산 미소비)")


def test_governor_concurrency():
    print("· 거버너 동시성 캡(max_concurrent=2)")
    g = RateGovernor(max_concurrent=2)
    cur = {"n": 0, "peak": 0}
    lk = threading.Lock()

    def work():
        with lk:
            cur["n"] += 1
            cur["peak"] = max(cur["peak"], cur["n"])
        time.sleep(0.15)
        with lk:
            cur["n"] -= 1
    gw = g.wrap(work)
    ts = [threading.Thread(target=gw) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    _check(cur["peak"] <= 2, f"동시 실행 최대 2 (peak={cur['peak']})")


def test_governor_rate():
    print("· 거버너 분당 상한(토큰버킷)")
    g = RateGovernor(rpm=120)            # 2/초, capacity=120 가득
    g.tokens = 2                          # 토큰 2개로 강제(빠른 검증)
    f = g.wrap(lambda: None)
    t0 = time.monotonic()
    for _ in range(4):                   # 2개는 즉시, 이후 2개는 ~0.5s 간격 대기
        f()
    dt = time.monotonic() - t0
    _check(dt >= 0.9, f"4회 호출이 토큰 보충 대기로 ≥0.9s (got {dt:.2f}s)")


def test_worker_pool():
    print("· 워커풀 큐/동시처리")
    from service import jobs

    def task(x, log):
        log(f"start {x}")
        time.sleep(0.2)
        log(f"done {x}")
        return x * 2
    ids = [jobs.submit(f"j{x}", task, x) for x in range(6)]
    _check(len(ids) == 6, "6개 제출 즉시 반환")
    # 폴링
    for _ in range(100):
        js = jobs.get_many(ids)
        if all(j.status in ("done", "error") for j in js):
            break
        time.sleep(0.1)
    js = jobs.get_many(ids)
    _check(all(j.status == "done" for j in js), "전부 done")
    _check([j.result for j in js] == [0, 2, 4, 6, 8, 10], "결과 정확")
    _check(all(len(j.logs) >= 2 for j in js), "진행 로그 캡처")
    print(f"    큐 상태: {jobs.queue_stats()}")


def main():
    print("워커풀 + 거버너 스모크\n")
    test_governor_budget()
    test_governor_concurrency()
    test_governor_rate()
    test_worker_pool()
    print("\n✅ 전부 통과 — 큐·동시처리·총예산·동시성캡·분당상한 정상.")


if __name__ == "__main__":
    main()
