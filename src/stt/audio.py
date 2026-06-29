"""오디오 유틸 — ffmpeg/ffprobe 래퍼(전사 전처리). 모델·API 무관, 순수 subprocess.

- 영상에서 오디오 추출(16kHz mono wav — STT 표준 입력, 용량↓)
- 길이(초) 측정
- 긴 오디오를 STT_CHUNK_SEC 단위 청크로 분할(겹침 포함)

ffmpeg 미설치 시 친절한 오류. 청킹 로직(경계·겹침 계산)은 ffmpeg 없이도 단위 테스트 가능하도록
순수 함수 plan_chunks() 로 분리한다.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src import config


@dataclass(frozen=True)
class Chunk:
    """오디오 청크 한 개. start_sec=원본 기준 시작초(타임스탬프 오프셋), index=순번."""
    index: int
    start_sec: float
    dur_sec: float
    path: Path | None = None     # 분할 산출 wav 경로(plan 단계에선 None)


def _require(tool: str) -> str:
    p = shutil.which(tool)
    if not p:
        raise RuntimeError(
            f"{tool} 가 필요합니다(오디오 처리). macOS: `brew install ffmpeg`, "
            f"Ubuntu: `apt-get install -y ffmpeg`."
        )
    return p


def is_video(path: Path) -> bool:
    return path.suffix.lower() in config.STT_VIDEO_EXTS


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in config.STT_AUDIO_EXTS


def probe_duration(path: Path) -> float:
    """오디오/영상 길이(초). ffprobe 사용."""
    ffprobe = _require("ffprobe")
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError as e:
        raise RuntimeError(f"길이 측정 실패: {path} (ffprobe 출력={out!r})") from e


def extract_audio(src: Path, dst: Path, *, sr: int = 16000) -> Path:
    """영상/오디오 → 16kHz mono wav 로 정규화(전사 입력 표준화)."""
    ffmpeg = _require("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr),
         "-f", "wav", str(dst)],
        capture_output=True, text=True, check=True,
    )
    return dst


def plan_chunks(duration_sec: float, *, chunk_sec: int | None = None,
                overlap_sec: int | None = None) -> list[Chunk]:
    """길이를 청크 경계로 쪼개는 계획(순수 함수 — ffmpeg 불필요, 테스트 용이).

    chunk_sec<=0 또는 길이<=chunk_sec 이면 통째 1청크. 겹침은 잘린 발화 복원용으로
    각 청크를 overlap 만큼 앞당겨 시작한다(중복 발화는 stitch 단계에서 정리).
    """
    chunk_sec = config.STT_CHUNK_SEC if chunk_sec is None else chunk_sec
    overlap_sec = config.STT_CHUNK_OVERLAP_SEC if overlap_sec is None else overlap_sec
    if duration_sec <= 0:
        return [Chunk(index=0, start_sec=0.0, dur_sec=0.0)]
    if chunk_sec <= 0 or duration_sec <= chunk_sec:
        return [Chunk(index=0, start_sec=0.0, dur_sec=round(duration_sec, 3))]

    chunks: list[Chunk] = []
    i, pos = 0, 0.0
    while pos < duration_sec:
        start = max(0.0, pos - (overlap_sec if i > 0 else 0))
        dur = min(chunk_sec + (pos - start), duration_sec - start)
        chunks.append(Chunk(index=i, start_sec=round(start, 3), dur_sec=round(dur, 3)))
        pos += chunk_sec
        i += 1
    return chunks


def slice_chunk(src_wav: Path, chunk: Chunk, dst: Path) -> Path:
    """plan_chunks 한 청크를 실제 wav 로 잘라낸다(ffmpeg -ss/-t)."""
    ffmpeg = _require("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-ss", str(chunk.start_sec), "-t", str(chunk.dur_sec),
         "-i", str(src_wav), "-ac", "1", "-ar", "16000", "-f", "wav", str(dst)],
        capture_output=True, text=True, check=True,
    )
    return dst
