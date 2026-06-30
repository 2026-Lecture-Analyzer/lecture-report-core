"""STT 오케스트레이터 — 녹화 파일 → transcript txt(기존 파이프라인 입력 포맷).

흐름: (영상이면 오디오 추출) → 길이 측정 → 청크 분할 → 청크별 transcribe_fn 전사
     → 청크 시작초 오프셋 + 겹침 중복 제거 → `<HH:MM:SS> 화자ID(hex): text` 조립.

모델 호출은 transcribe_fn 주입 → 조립 로직(assemble_lines)은 순수 함수라 ffmpeg/오디오/키
없이 단위 검증 가능(scripts/smoke_stt.py).

체크포인트: 청크 전사 결과를 work_dir 에 chunk_{i}.json 으로 저장 → 끊겨도 이어서 재개.
"""
from __future__ import annotations

import json
from pathlib import Path

from src import config
from src.stt import audio as A
from src.stt.prompts import parse_segments, transcribe_messages


# ── 순수 헬퍼(테스트 용이) ─────────────────────────────────────────────────
def start_seconds(start_time: str) -> int:
    """'HH:MM:SS' → 자정 기준 초."""
    h, m, s = (int(x) for x in start_time.split(":"))
    return h * 3600 + m * 60 + s


def fmt_ts(abs_sec: float) -> str:
    """절대 초 → '<HH:MM:SS>' 본문용 'HH:MM:SS'(24h, 2자리). 24h 넘으면 wrap."""
    t = int(abs_sec) % (24 * 3600)
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def spk_to_hex(spk: int) -> str:
    """화자 정수 → parse 가 받는 hex 화자ID(8자리). 0=강사, 1+=학생."""
    return f"{int(spk):08x}"


def offset_and_dedup(segments: list[dict], chunk: A.Chunk,
                     overlap_sec: float) -> list[dict]:
    """청크-상대 세그먼트 → 원본-절대(t += start_sec). 겹침 구간 중복 제거.

    i>0 청크는 앞 overlap_sec 가 직전 청크 꼬리와 겹치므로 상대 t<overlap 은 버린다.
    """
    drop_below = overlap_sec if chunk.index > 0 else 0.0
    out = []
    for seg in segments:
        if seg["t"] < drop_below:
            continue
        out.append({"t": round(seg["t"] + chunk.start_sec, 3),
                    "spk": seg["spk"], "text": seg["text"]})
    return out


def assemble_lines(per_chunk: list[list[dict]], chunks: list[A.Chunk], *,
                   start_time: str = None, overlap_sec: int = None) -> list[str]:
    """청크별 세그먼트 묶음 → 최종 transcript 라인들(순수 함수).

    per_chunk[i] 는 chunks[i] 의 (청크-상대) 세그먼트. 오프셋·중복제거·정렬 후
    '<HH:MM:SS> 화자ID(hex): text' 로 포맷한다.
    """
    start_time = start_time or config.STT_START_TIME
    overlap_sec = config.STT_CHUNK_OVERLAP_SEC if overlap_sec is None else overlap_sec
    base = start_seconds(start_time)

    merged: list[dict] = []
    for segs, ch in zip(per_chunk, chunks):
        merged.extend(offset_and_dedup(segs, ch, overlap_sec))
    merged.sort(key=lambda s: s["t"])

    lines = []
    for seg in merged:
        txt = seg["text"].strip()
        if not txt:
            continue
        lines.append(f"<{fmt_ts(base + seg['t'])}> {spk_to_hex(seg['spk'])}: {txt}")
    return lines


# ── 전체 파이프라인(ffmpeg + 모델) ────────────────────────────────────────
def transcribe_media(src: Path, *, date: str, course: str, transcribe_fn,
                     out_dir: Path = None, work_dir: Path = None,
                     start_time: str = None, chunk_sec: int = None,
                     overlap_sec: int = None, resume: bool = True,
                     log=print) -> Path:
    """녹화 파일 1개 → transcript txt(`{date}_{course}.txt`) 경로 반환.

    transcribe_fn(audio_path, messages)->str 를 주입받는다(모델 무관).
    """
    src = Path(src)
    out_dir = Path(out_dir or config.SCRIPT_DIR)
    work_dir = Path(work_dir or (config.PROCESSED_DIR / "_stt" / f"{date}_{course}"))
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    start_time = start_time or config.STT_START_TIME
    overlap_sec = config.STT_CHUNK_OVERLAP_SEC if overlap_sec is None else overlap_sec

    # 1) 영상이면 오디오 추출 → 16kHz mono wav 로 표준화
    if A.is_video(src):
        log(f"① 영상 → 오디오 추출: {src.name}")
        wav = A.extract_audio(src, work_dir / "audio.wav")
    elif A.is_audio(src):
        wav = A.extract_audio(src, work_dir / "audio.wav")  # 포맷·샘플레이트 통일
    else:
        raise ValueError(f"지원하지 않는 입력: {src.suffix} (오디오/영상만)")

    # 2) 길이 측정 → 청크 계획
    dur = A.probe_duration(wav)
    chunks = A.plan_chunks(dur, chunk_sec=chunk_sec, overlap_sec=overlap_sec)
    log(f"② 길이 {dur:.0f}s → {len(chunks)}청크(각 ~{config.STT_CHUNK_SEC if chunk_sec is None else chunk_sec}s)")

    # 3) 청크별 전사(체크포인트/재개)
    per_chunk: list[list[dict]] = []
    for ch in chunks:
        ckpt = work_dir / f"chunk_{ch.index:03d}.json"
        if resume and ckpt.exists():
            per_chunk.append(json.loads(ckpt.read_text(encoding="utf-8")))
            log(f"  ↩︎ 청크 {ch.index} 재사용(체크포인트)")
            continue
        cwav = A.slice_chunk(wav, ch, work_dir / f"chunk_{ch.index:03d}.wav")
        log(f"  ▶︎ 청크 {ch.index} 전사(과금)… [{ch.start_sec:.0f}s~]")
        raw = transcribe_fn(cwav, transcribe_messages())
        segs = parse_segments(raw)
        ckpt.write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
        per_chunk.append(segs)
        try:
            cwav.unlink()      # 청크 wav 정리(용량)
        except OSError:
            pass

    # 4) 조립 → 파일 쓰기
    lines = assemble_lines(per_chunk, chunks, start_time=start_time, overlap_sec=overlap_sec)
    out_txt = out_dir / f"{date}_{course}.txt"
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"③ transcript {len(lines)}발화 → {out_txt}")
    return out_txt
