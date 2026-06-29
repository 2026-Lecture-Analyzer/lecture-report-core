"""STT 로컬 러너 — 녹화 파일(오디오/영상) → transcript txt(기존 파이프라인 입력).

Gemini 오디오 네이티브로 전사·화자분리 → `<HH:MM:SS> 화자ID(hex): text`.
산출 txt 는 강의 스크립트 폴더(config.SCRIPT_DIR)에 떨어지므로, 곧바로
`python -m scripts.run_preprocess` → refine → analyze 로 이어진다.

비용 안전장치(실제 Gemini 호출 = 과금):
    --dry-run        오디오 추출·청크 계획만(모델 호출 0). 길이·청크수·예상 호출 확인.
    --chunk-sec N    청크 길이(초) 조정(기본 config.STT_CHUNK_SEC=600).
    --max-chunks N   앞 N청크만 전사(맛보기).

사용법:
    python -m scripts.run_stt_local lecture.mp4 --date 2026-02-05 --course kdt-backendj-21th
    python -m scripts.run_stt_local lecture.m4a --dry-run        # 호출 없이 계획만
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.stt import audio as A  # noqa: E402
from src.stt.transcribe import transcribe_media  # noqa: E402

_FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")


def _infer_date_course(media: Path, date: str | None, course: str | None):
    """파일명이 'YYYY-MM-DD_course.*' 면 자동 추론, 아니면 플래그 필수."""
    if date and course:
        return date, course
    m = _FNAME_RE.match(media.stem)
    if m:
        return date or m.group(1), course or m.group(2)
    raise SystemExit(
        "파일명에서 날짜/과목을 못 읽었습니다. --date YYYY-MM-DD --course <id> 를 주거나 "
        "파일명을 'YYYY-MM-DD_course.mp4' 로 맞추세요."
    )


def main():
    ap = argparse.ArgumentParser(description="녹화 파일 → transcript txt (Gemini STT)")
    ap.add_argument("media", help="오디오/영상 파일 경로(mp3/wav/m4a/mp4/mov ...)")
    ap.add_argument("--date", help="강의 날짜 YYYY-MM-DD (파일명에서 추론 가능)")
    ap.add_argument("--course", help="과목 id (파일명에서 추론 가능)")
    ap.add_argument("--start", default=config.STT_START_TIME, help="녹화 시작 월클럭(기본 09:00:00)")
    ap.add_argument("--chunk-sec", type=int, default=None, help="청크 길이(초)")
    ap.add_argument("--max-chunks", type=int, default=None, help="앞 N청크만(맛보기)")
    ap.add_argument("--out-dir", default=None, help="transcript 출력 폴더(기본 SCRIPT_DIR)")
    ap.add_argument("--backend", default=None, help="STT 백엔드(기본 config.STT_BACKEND=google)")
    ap.add_argument("--no-resume", action="store_true", help="체크포인트 무시하고 처음부터")
    ap.add_argument("--dry-run", action="store_true", help="모델 호출 없이 오디오·청크 계획만")
    args = ap.parse_args()

    media = Path(args.media)
    if not media.exists():
        raise SystemExit(f"파일 없음: {media}")
    date, course = _infer_date_course(media, args.date, args.course)

    if args.dry_run:
        work = config.PROCESSED_DIR / "_stt" / f"{date}_{course}"
        wav = A.extract_audio(media, work / "audio.wav")
        dur = A.probe_duration(wav)
        chunks = A.plan_chunks(dur, chunk_sec=args.chunk_sec)
        print(f"[dry-run] {media.name}")
        print(f"  길이      : {dur:.0f}s ({dur/60:.1f}분)")
        print(f"  청크      : {len(chunks)}개 (각 ~{args.chunk_sec or config.STT_CHUNK_SEC}s)")
        print(f"  예상 호출 : {len(chunks)}회 Gemini 전사 (과금)")
        print(f"  출력 예정 : {Path(args.out_dir or config.SCRIPT_DIR) / f'{date}_{course}.txt'}")
        return

    from src.stt.model import make_transcribe_fn  # 지연 import(키 필요)
    base_fn = make_transcribe_fn(backend=args.backend)

    # --max-chunks: 앞 N청크만 전사(나머지 청크는 빈 결과로 처리)
    if args.max_chunks is not None:
        limit = args.max_chunks

        def transcribe_fn(audio_path, messages, _i=[0]):
            if _i[0] >= limit:
                return "[]"
            _i[0] += 1
            return base_fn(audio_path, messages)
    else:
        transcribe_fn = base_fn

    out = transcribe_media(
        media, date=date, course=course, transcribe_fn=transcribe_fn,
        out_dir=Path(args.out_dir) if args.out_dir else None,
        start_time=args.start, chunk_sec=args.chunk_sec,
        resume=not args.no_resume,
    )
    print(f"\n✅ transcript 생성: {out}")
    print("다음: python -m scripts.run_preprocess  → run_refine_local → run_analyze_local")


if __name__ == "__main__":
    main()
