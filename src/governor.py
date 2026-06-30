"""전역 LLM 호출 거버너 — 토큰버킷(분당 호출 상한) + 총 예산 + 동시성 캡.

외부 LLM API rate limit·비용을 시스템 전역에서 방어한다. 워커가 몇 개든, job 이 몇 개든
**모든 LLM 호출이 이 거버너를 통과**해 분당 상한·총 호출수·동시 호출수를 넘지 않게 한다.

기본은 무제한(rpm=0) — 켜야(set_limits) 동작. 스레드 안전. wrap(fn) 으로 generate_fn 감쌈.
"""
from __future__ import annotations

import os
import threading
import time


class BudgetExceeded(RuntimeError):
    """총 호출 예산 소진."""


class RateGovernor:
    def __init__(self, rpm: int = 0, total_budget: int = 0, max_concurrent: int = 0):
        # rpm=분당 호출 상한(0=무제한), total_budget=총 허용 호출(0=무제한), max_concurrent=동시 호출(0=무제한)
        self._lock = threading.Lock()
        self.used = 0                       # 누적 호출수
        self.set_limits(rpm, total_budget, max_concurrent)

    def set_limits(self, rpm: int = None, total_budget: int = None, max_concurrent: int = None):
        with getattr(self, "_lock", threading.Lock()):
            if rpm is not None:
                self.rpm = rpm
                self.capacity = max(rpm, 1)
                self.tokens = float(self.capacity)
                self.refill_per_sec = rpm / 60.0 if rpm > 0 else 0.0
                self.last = time.monotonic()
            if total_budget is not None:
                self.total_budget = total_budget
            if max_concurrent is not None:
                self.max_concurrent = max_concurrent
                self._sem = threading.Semaphore(max_concurrent) if max_concurrent > 0 else None

    def _take_token(self):
        """rpm 토큰버킷 — 토큰 1개 확보될 때까지 대기(블로킹)."""
        if self.rpm <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.refill_per_sec)
                self.last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                need = (1 - self.tokens) / self.refill_per_sec
            time.sleep(min(need, 1.0))

    def acquire(self):
        """LLM 호출 1건 권리 확보 — 총예산 체크 → 분당 토큰 → (동시성 캡은 wrap 에서)."""
        with self._lock:
            if self.total_budget > 0 and self.used >= self.total_budget:
                raise BudgetExceeded(f"총 호출 예산 {self.total_budget} 소진")
            self.used += 1
        self._take_token()

    def wrap(self, fn):
        """generate_fn/transcribe_fn 을 감싸 매 호출 전 거버너 통과."""
        def governed(*args, **kwargs):
            sem = self._sem
            if sem is not None:
                sem.acquire()
            try:
                self.acquire()
                return fn(*args, **kwargs)
            finally:
                if sem is not None:
                    sem.release()
        return governed

    def stats(self) -> dict:
        with self._lock:
            return {"rpm": self.rpm, "used": self.used, "total_budget": self.total_budget,
                    "max_concurrent": self.max_concurrent,
                    "remaining": (self.total_budget - self.used) if self.total_budget > 0 else None}


# 전역 싱글톤 — 환경변수로 초기화(미설정=무제한).
GOVERNOR = RateGovernor(
    rpm=int(os.environ.get("LLM_RPM", "0")),
    total_budget=int(os.environ.get("LLM_TOTAL_BUDGET", "0")),
    max_concurrent=int(os.environ.get("LLM_MAX_CONCURRENT", "0")),
)


def govern(fn):
    """전역 거버너로 fn 감싸기(편의)."""
    return GOVERNOR.wrap(fn)
