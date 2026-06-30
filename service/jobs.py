"""인프로세스 작업 큐 + 워커풀 — 분석을 요청 스레드에서 분리(동시 접속 비블로킹).

ThreadPoolExecutor 가 워커풀(고정 N) + 내부 큐: submit 하면 큐에 쌓이고 빈 워커가 꺼내 실행.
job 상태·진행로그·결과를 메모리 레지스트리에 보관 → UI 가 폴링. 업로드는 즉시 반환되고
무거운 LLM 파이프라인은 백그라운드 워커가 처리.

스케일 노트: 단일 인스턴스용. 멀티노드는 Redis/RQ + 별도 워커 + 키 볼트(per-call 키)로 진화.
키(BYO)는 submit 시점 캡처해 메모리로만 워커에 전달(디스크 미저장). LLM 호출은 전역 거버너 통과.
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

POOL_SIZE = int(os.environ.get("LECTURE_WORKERS", "3"))   # 워커 수(큐 동시 처리)
_executor = ThreadPoolExecutor(max_workers=POOL_SIZE, thread_name_prefix="lec-worker")
_jobs: dict[str, "Job"] = {}
_lock = threading.Lock()
_seq = 0


@dataclass
class Job:
    id: str
    name: str
    status: str = "queued"          # queued | running | done | error
    logs: list = field(default_factory=list)
    result: object = None
    error: str = ""
    submitted_at: float = 0.0
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def elapsed(self) -> float:
        end = self.ended_at or time.monotonic()
        return (end - self.started_at) if self.started_at else 0.0


def submit(name: str, target, *args, **kwargs) -> str:
    """target(*args, log=callable, **kwargs) 를 워커풀에 제출. job_id 반환(즉시).

    target 은 진행 로그용 log 콜러블을 키워드로 받는다. 반환값은 job.result 에 저장.
    """
    global _seq
    with _lock:
        _seq += 1
        jid = f"job-{_seq}"
        job = Job(id=jid, name=name, submitted_at=time.monotonic())
        _jobs[jid] = job

    def _run():
        job.started_at = time.monotonic()
        job.status = "running"

        def log(m):
            job.logs.append(str(m))

        try:
            job.result = target(*args, log=log, **kwargs)
            job.status = "done"
        except Exception as e:  # noqa: BLE001
            job.error = f"{type(e).__name__}: {e}"
            job.logs.append("❌ " + job.error)
            job.status = "error"
        finally:
            job.ended_at = time.monotonic()

    _executor.submit(_run)
    return jid


def get(jid: str) -> "Job | None":
    return _jobs.get(jid)


def get_many(jids: list[str]) -> list["Job"]:
    return [_jobs[j] for j in jids if j in _jobs]


def queue_stats() -> dict:
    with _lock:
        st = [j.status for j in _jobs.values()]
    return {"workers": POOL_SIZE,
            "queued": st.count("queued"), "running": st.count("running"),
            "done": st.count("done"), "error": st.count("error")}


def clear_finished(jids: list[str]) -> None:
    with _lock:
        for j in jids:
            job = _jobs.get(j)
            if job and job.status in ("done", "error"):
                _jobs.pop(j, None)
