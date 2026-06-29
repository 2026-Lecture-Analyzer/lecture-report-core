"""라이브 강의 세션 — 실시간 코칭(넛지+부분점수 게이지) → 종료 시 최종 평가·정제대본 확정.

흐름:
  [스트리밍 중]  윈도우마다 전사 → 라이브 넛지 + 부분점수 게이지(메트릭 5항목, 잠정)
  [종료 후]      누적 발화 → batch(정제·청킹·holistic 분석) → 18항목 최종 점수 + 정제 대본
                 → 기존 대시보드(src/report/dashboard.py)가 읽는 scores/analysis/chunks 산출

실시간=신호(넛지)+부분점수, 최종=18항목 확정+정제대본. 같은 채점 로직이라 잠정→최종 일관.

비용 안전장치:
    --max-sec N         앞 N초만(스트리밍 윈도우당 1회 + 종료 후 batch).
    --self-consistency  분석 반복(기본 1=싸게).

사용법:
    python -m scripts.run_live_session "../data/0318 클라우드컴퓨팅- 03-1 가상화기술.m4a" \
        --date 2025-03-18 --course 클라우드컴퓨팅 --max-sec 180
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service import pipeline  # noqa: E402
from src.live.nudge import LiveConfig  # noqa: E402
from src.live.score import gauge_bar, live_partial_score  # noqa: E402
from src.live.stream import StreamConfig, run_stream  # noqa: E402
from src.scoring.scoring import compute_scores, save_scores  # noqa: E402
from src.stt.transcribe import fmt_ts, spk_to_hex, start_seconds  # noqa: E402

_ICON = {"warn": "🔴", "info": "🟡"}


def _fmt(sec: int) -> str:
    return f"{sec//60:02d}:{sec%60:02d}"


def _to_transcript(utterances, start_clock="09:00:00") -> str:
    base = start_seconds(start_clock)
    return "\n".join(f"<{fmt_ts(base + s)}> {spk_to_hex(0)}: {t}" for s, t in utterances) + "\n"


def _refined_text(clean_path: Path) -> str:
    if not clean_path.exists():
        return ""
    rows = [json.loads(l) for l in clean_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return "\n\n".join(r.get("clean_text", "") for r in rows if r.get("clean_text"))


def main():
    ap = argparse.ArgumentParser(description="라이브 강의 세션(실시간 코칭 → 최종 확정)")
    ap.add_argument("media")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--course", required=True)
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--max-sec", type=float, default=None)
    ap.add_argument("--min-gap", type=int, default=120)
    ap.add_argument("--self-consistency", type=int, default=1)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    media = Path(args.media)
    if not media.exists():
        raise SystemExit(f"파일 없음: {media}")
    out_dir = Path(args.out_dir or (Path("outputs/_live_session") / f"{args.date}_{args.course}"))
    out_dir.mkdir(parents=True, exist_ok=True)

    from src.stt.model import make_transcribe_fn
    tfn = make_transcribe_fn()

    print(f"=== 🔴 LIVE 세션: {media.name} ===")
    print("실시간: 코칭 넛지 + 부분점수(메트릭 5항목) · 종료 후: 18항목 최종확정 + 정제대본\n")
    last_gauge = {"v": None}

    def on_nudge(n):
        print(f"  ⏱[{_fmt(n.sec)}] {_ICON.get(n.severity,'•')} {n.message}")

    def on_window(idx, start, utts):
        ps = live_partial_score(utts)
        pt = ps["partial_total"]
        if pt is not None:
            print(f"  📊[{_fmt(int(utts[-1][0]))}] 부분점수 {pt:.0f}/100 "
                  f"{gauge_bar(pt)} (메트릭 {ps['covered']}/18항목)")
            last_gauge["v"] = ps

    res = run_stream(media, transcribe_fn=tfn, on_nudge=on_nudge, on_window=on_window,
                     stream_cfg=StreamConfig(window_sec=args.window, max_sec=args.max_sec),
                     nudge_cfg=LiveConfig(window_sec=max(180, args.window * 3)),
                     digest=True, min_gap_sec=args.min_gap,
                     log=lambda m: print(f"[{m}]"))
    utts = res["utterances"]
    print(f"\n— 스트리밍 종료: 발화 {len(utts)}건 · 라이브 넛지 {len(res['nudges'])}건 —\n")

    # ── 종료 후: 정제 + 18항목 최종 평가(batch) ──
    print("⏳ 최종 확정 중(정제·청킹·holistic 분석)…")
    transcript = _to_transcript(utts)
    (out_dir / "transcript_raw.txt").write_text(transcript, encoding="utf-8")
    grouped = pipeline.run_real(transcript, date=args.date, course=args.course,
                                mode="single", self_consistency=args.self_consistency,
                                log=lambda m: print(f"  {m}"))
    rows = [r for p in grouped.values() for r in p["rows"]]
    scores = compute_scores(rows)
    save_scores(scores, out_dir / "scores.json")

    # work 산출(analysis/chunks/clean)을 대시보드 폴더로 복사
    work = pipeline.CORE / "reports" / "_work" / pipeline._stem(args.date, args.course) / "processed"
    for f in ("analysis.jsonl", "chunks.jsonl", "clean.jsonl"):
        if (work / f).exists():
            shutil.copy(work / f, out_dir / f)
    refined = _refined_text(out_dir / "clean.jsonl")
    (out_dir / "refined_transcript.txt").write_text(refined, encoding="utf-8")

    final_total = scores.get("summary", {}).get("avg_total")
    partial = last_gauge["v"]["partial_total"] if last_gauge["v"] else None
    print("\n=== ✅ 최종 확정 ===")
    if partial is not None and final_total is not None:
        print(f"  부분점수(실시간 메트릭 5항목): {partial:.0f}/100")
    print(f"  최종 강의력 점수(18항목 확정)  : {final_total}/100")
    print(f"  정제 대본: {out_dir/'refined_transcript.txt'} ({len(refined)}자)")
    print(f"\n📂 대시보드로 보기:")
    print(f"  .venv/bin/streamlit run src/report/dashboard.py")
    print(f"  사이드바 경로를 아래로 변경:")
    for f in ("scores.json", "analysis.jsonl", "chunks.jsonl"):
        print(f"    {(out_dir / f).resolve()}")


if __name__ == "__main__":
    main()
