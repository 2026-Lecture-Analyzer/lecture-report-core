"""라이브 넛지 시뮬 러너 — transcript 를 시간순 리플레이해 '실시간이면 떴을' 넛지 타임라인 출력.

실제 스트리밍/마이크 없이, 기존 transcript 로 실시간 코칭의 이점(언제 무엇을 교정했을지)을 실증.
넛지는 raw 메트릭(필러·지배필러·속도·이해확인 침묵·도입목표)만 — 실시간 가능한 부분.

사용법:
    python -m scripts.run_live_sim outputs/_stt_test/2025-03-18_클라우드컴퓨팅.txt
    python -m scripts.run_live_sim <txt> --window 120 --cooldown 90
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.live.nudge import LiveConfig, coalesce, parse_transcript, simulate  # noqa: E402

_ICON = {"warn": "🔴", "info": "🟡"}


def _fmt(sec: int) -> str:
    return f"{sec//60:02d}:{sec%60:02d}"


def main():
    ap = argparse.ArgumentParser(description="라이브 넛지 시뮬레이션")
    ap.add_argument("transcript", help="transcript txt 경로")
    ap.add_argument("--window", type=int, default=180, help="롤링 윈도우(초)")
    ap.add_argument("--cooldown", type=int, default=120, help="동일 규칙 재발화 최소 간격(초)")
    ap.add_argument("--grace", type=int, default=300, help="도입 학습목표 유예(초)")
    ap.add_argument("--silence", type=int, default=600, help="이해확인 침묵 임계(초)")
    ap.add_argument("--digest", action="store_true",
                    help="우선순위 병합 — '한 번에 가장 중요한 1건'만(넛지 피로 억제)")
    ap.add_argument("--min-gap", type=int, default=150, help="(digest) 넛지 최소 간격(초)")
    args = ap.parse_args()

    path = Path(args.transcript)
    if not path.exists():
        raise SystemExit(f"파일 없음: {path}")
    utt = parse_transcript(path.read_text(encoding="utf-8"))
    if not utt:
        raise SystemExit("파싱된 발화가 없습니다(포맷 확인).")
    dur = utt[-1][0]
    cfg = LiveConfig(window_sec=args.window, cooldown_sec=args.cooldown,
                     objective_grace_sec=args.grace, check_silence_sec=args.silence)
    raw = simulate(utt, cfg)
    nudges = coalesce(raw, min_gap_sec=args.min_gap) if args.digest else raw

    print(f"=== 라이브 코칭 시뮬: {path.name} ===")
    print(f"강의 길이 {_fmt(dur)} · 발화 {len(utt)}건 · 윈도우 {args.window}s · 쿨다운 {args.cooldown}s")
    if args.digest:
        print(f"[digest] 우선순위 병합 — 원본 {len(raw)}건 → {len(nudges)}건 "
              f"(최소간격 {args.min_gap}s, 한 번에 1건)")
    print(f"\n⏱  타임라인 — 라이브였다면 강사가 본 넛지 ({len(nudges)}건)\n")
    for n in nudges:
        print(f"  [{_fmt(n.sec)}] {_ICON.get(n.severity,'•')} {n.message}")

    by_rule = Counter(n.rule for n in nudges)
    print("\n📊 규칙별 발화 횟수:")
    for rule, c in by_rule.most_common():
        print(f"  - {rule}: {c}회")
    mins = max(dur / 60, 1)
    print(f"\n넛지 밀도: {len(nudges)/mins:.2f}건/분  "
          f"(너무 잦으면 윈도우↑·쿨다운↑ 로 조절)")
    print("\n※ holistic 항목(구조성·요약·개념정의 등)은 전체 통독 필요 → 강의 후 batch 리포트가 담당.")


if __name__ == "__main__":
    main()
