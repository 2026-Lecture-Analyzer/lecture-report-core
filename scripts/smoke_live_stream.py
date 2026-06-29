"""스트리밍 라이브 코칭 스모크 — stub 전사 + 합성 wav 로 온라인 루프 검증(API 0).

ffmpeg 로 무음 wav 생성 → 윈도우 슬라이스 경로까지 실제로 타되, 전사는 stub 로 대체.
사용: python -m scripts.smoke_live_stream
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.live.nudge import LiveConfig, Nudge, OnlineGate  # noqa: E402
from src.live.stream import StreamConfig, run_stream  # noqa: E402


def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ✓ {msg}")


def test_online_gate():
    print("· OnlineGate — 온라인 병합/최소간격")
    g = OnlineGate(min_gap_sec=150, cluster_sec=30)
    out = []
    out += g.offer(Nudge(10, "filler", "warn", "f", 0.1))
    out += g.offer(Nudge(15, "dominant", "warn", "d", 0.2))   # 같은 클러스터
    out += g.offer(Nudge(200, "pace", "warn", "p", 0.3))      # 클러스터 밖 → 직전 flush
    out += g.close()
    rules = [n.rule for n in out]
    _check(rules == ["dominant", "pace"], f"클러스터 best(dominant)+pace flush (got {rules})")
    _check(out[1].sec - out[0].sec >= 150, "최소간격 보장")


def test_stream_loop():
    print("· run_stream 온라인 루프(stub 전사 + 합성 wav)")
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "2025-03-18_test.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                    "-t", "60", str(src)], capture_output=True, check=True)

    # stub: 윈도우마다 '이렇게' 도배 발화(필러 넛지 유도). start_sec 기준 상대 t.
    def stub(wav_path, messages):
        return json.dumps([{"t": 1.0, "spk": 0, "text": "이렇게 이렇게 막 이제 그래서 이렇게 봅니다"},
                           {"t": 10.0, "spk": 0, "text": "이렇게 또 이렇게 데이터를 이렇게"}],
                          ensure_ascii=False)

    nudges_live = []
    res = run_stream(src, transcribe_fn=stub,
                     on_nudge=lambda n: nudges_live.append(n),
                     stream_cfg=StreamConfig(window_sec=20),
                     nudge_cfg=LiveConfig(window_sec=60, min_words=10, cooldown_sec=30,
                                          objective_grace_sec=10**9, check_silence_sec=10**9),
                     digest=True, min_gap_sec=60, log=lambda *a: None)
    _check(len(res["utterances"]) > 0, f"발화 수집됨 ({len(res['utterances'])})")
    _check(len(res["raw_nudges"]) > 0, "raw 넛지 발생(필러)")
    _check(len(res["nudges"]) <= len(res["raw_nudges"]), "digest 가 raw 이하로 억제")
    _check(nudges_live == res["nudges"], "on_nudge 콜백이 발화 시점에 호출됨(온라인)")
    _check(all(n.rule in ("filler", "dominant") for n in res["raw_nudges"]),
           "필러/지배필러 넛지만(무음+stub 조건)")


def main():
    print("스트리밍 라이브 코칭 스모크\n")
    test_online_gate()
    test_stream_loop()
    print("\n✅ 전부 통과 — 온라인 루프·게이트·윈도우 슬라이스 정상(API 0).")


if __name__ == "__main__":
    main()
