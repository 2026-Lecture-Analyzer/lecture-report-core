"""실시간(near-RT) 라이브 코칭 스트리밍 — 녹화/오디오를 윈도우 단위로 흘려 넛지를 즉시 출력.

전체 녹화를 기다리지 않고, 윈도우(기본 20s)가 전사되는 대로 라이브 넛지를 발화한다(온라인).
전사는 Gemini(배치 transcribe_fn)를 윈도우마다 호출 — 지연 = 윈도우 길이.
진짜 bidi Live(input 전사)는 가용 모델 제약으로 보류, transcriber 교체만 하면 승계됨.

비용 안전장치:
    --max-sec N     앞 N초만 스트리밍(윈도우당 1 Gemini 호출 = N/window 회).
    --window S      윈도우 길이(초). 작을수록 저지연·호출↑.
    --no-digest     억제 없이 모든 넛지(원시).

사용법:
    python -m scripts.run_live_stream "../data/0318 클라우드컴퓨팅- 03-1 가상화기술.m4a" --max-sec 180
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.live.nudge import LiveConfig  # noqa: E402
from src.live.stream import StreamConfig, run_stream  # noqa: E402

_ICON = {"warn": "🔴", "info": "🟡"}


def _fmt(sec: int) -> str:
    return f"{sec//60:02d}:{sec%60:02d}"


def main():
    ap = argparse.ArgumentParser(description="near-real-time 라이브 코칭 스트리밍")
    ap.add_argument("media", help="오디오/영상 파일")
    ap.add_argument("--window", type=int, default=20, help="윈도우(초) = 지연")
    ap.add_argument("--max-sec", type=float, default=None, help="앞 N초만(비용 제한)")
    ap.add_argument("--min-gap", type=int, default=150, help="(digest) 넛지 최소 간격(초)")
    ap.add_argument("--no-digest", action="store_true", help="억제 없이 모든 넛지")
    args = ap.parse_args()

    media = Path(args.media)
    if not media.exists():
        raise SystemExit(f"파일 없음: {media}")

    from src.stt.model import make_transcribe_fn
    tfn = make_transcribe_fn()

    print(f"=== 🔴 LIVE 코칭 스트리밍: {media.name} ===")
    print(f"윈도우 {args.window}s · digest {'OFF' if args.no_digest else 'ON'}"
          f"{'' if args.max_sec is None else f' · 앞 {args.max_sec:.0f}s'}\n")

    def on_nudge(n):    # 발화 시점(온라인)에 즉시 출력 — 강사 화면 흉내
        print(f"  ⏱[{_fmt(n.sec)}] {_ICON.get(n.severity,'•')} {n.message}")

    res = run_stream(
        media, transcribe_fn=tfn, on_nudge=on_nudge,
        stream_cfg=StreamConfig(window_sec=args.window, max_sec=args.max_sec),
        nudge_cfg=LiveConfig(window_sec=max(180, args.window * 3)),
        digest=not args.no_digest, min_gap_sec=args.min_gap,
        log=lambda m: print(f"[{m}]"),
    )
    by = Counter(n.rule for n in res["nudges"])
    print(f"\n📊 발화 넛지 {len(res['nudges'])}건(raw {len(res['raw_nudges'])}) · "
          f"발화 {len(res['utterances'])}건")
    for r, c in by.most_common():
        print(f"  - {r}: {c}")
    print("\n※ 온라인 처리 — 녹화 전체를 기다리지 않고 윈도우마다 넛지 발화. "
          "holistic 18항목 심층평가는 강의 후 batch 리포트가 담당.")


if __name__ == "__main__":
    main()
