"""near-real-time 스트리밍 — 오디오 윈도우를 온라인으로 전사→넛지(라이브 코칭).

진짜 bidi Live API(input 전사)는 현재 키로 가용한 모델이 native-audio(AUDIO 전용)뿐이라
깔끔히 안 나옴 → 동일 가치를 주는 **청크 스트리밍**으로 구현: 짧은 윈도우(기본 20s)를
도착하는 대로 배치 transcribe_fn 으로 전사하고, 누적 발화를 라이브 넛지 엔진에 흘려보낸다.
지연 = 윈도우 길이(~20s)로, 코칭 넛지(필러·속도·침묵)엔 충분.

transcriber 는 주입(인터페이스 동일) → 추후 Live 모델이 되면 transcribe_window 만 교체.
온라인 구조라 전체 녹화를 기다리지 않고 진행 중 넛지를 낸다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src import config
from src.live.nudge import LiveConfig, Nudge, OnlineGate, _Engine
from src.stt import audio as A
from src.stt.prompts import parse_segments, transcribe_messages


@dataclass
class StreamConfig:
    window_sec: int = 20            # 한 번에 전사할 오디오 윈도우(=지연)
    max_sec: float | None = None    # 앞 N초만(맛보기·비용 제한)
    start_clock: str = None         # 타임라인 표시 기준(미사용시 0:00부터)


def iter_windows(media: Path, *, window_sec: int, max_sec: float = None,
                 work_dir: Path = None, log=print):
    """녹화 파일을 window_sec 단위 wav 청크로 잘라 (idx, start_sec, wav_path) 순차 산출.

    한 번 16k mono wav 로 정규화한 뒤 윈도우별로 슬라이스(실시간 캡처를 흉내).
    """
    media = Path(media)
    work_dir = Path(work_dir or (config.PROCESSED_DIR / "_stream" / media.stem))
    work_dir.mkdir(parents=True, exist_ok=True)
    wav = A.extract_audio(media, work_dir / "audio.wav")
    dur = A.probe_duration(wav)
    if max_sec:
        dur = min(dur, max_sec)
    n = int(dur // window_sec) + (1 if dur % window_sec else 0)
    log(f"스트림: 길이 {dur:.0f}s → {n}윈도우(각 {window_sec}s)")
    for i in range(n):
        start = i * window_sec
        chunk = A.Chunk(index=i, start_sec=float(start),
                        dur_sec=float(min(window_sec, dur - start)))
        if chunk.dur_sec <= 0:
            break
        cwav = A.slice_chunk(wav, chunk, work_dir / f"win_{i:04d}.wav")
        yield i, float(start), cwav


def transcribe_window(wav: Path, transcribe_fn, start_sec: float) -> list[tuple[int, str]]:
    """윈도우 wav → [(절대초, 발화)]. start_sec 만큼 윈도우-상대 시각을 민다."""
    segs = parse_segments(transcribe_fn(wav, transcribe_messages()))
    return [(int(start_sec + s["t"]), s["text"]) for s in segs]


def run_stream(media: Path, *, transcribe_fn, on_nudge=None, on_text=None, on_window=None,
               stream_cfg: StreamConfig = None, nudge_cfg: LiveConfig = None,
               digest: bool = True, min_gap_sec: int = 150, log=print) -> dict:
    """온라인 스트리밍 루프: 윈도우 도착마다 전사→넛지 엔진 feed→(digest면 게이트)→on_nudge.

    on_window(idx, start_sec, utterances) 는 각 윈도우 처리 후 호출(부분점수 갱신용).
    반환 {"utterances":[(sec,text)], "nudges":[Nudge](발화된 것), "raw_nudges":[...]}.
    """
    scfg = stream_cfg or StreamConfig()
    eng = _Engine(nudge_cfg or LiveConfig())
    gate = OnlineGate(min_gap_sec=min_gap_sec) if digest else None
    utterances: list[tuple[int, str]] = []
    emitted: list[Nudge] = []
    raw: list[Nudge] = []

    def _emit(n: Nudge):
        emitted.append(n)
        if on_nudge:
            on_nudge(n)

    for idx, start, cwav in iter_windows(media, window_sec=scfg.window_sec,
                                         max_sec=scfg.max_sec, log=log):
        utts = transcribe_window(cwav, transcribe_fn, start)
        try:
            cwav.unlink()
        except OSError:
            pass
        for sec, text in utts:
            utterances.append((sec, text))
            if on_text:
                on_text(sec, text)
            for n in eng.feed(sec, text):
                raw.append(n)
                if gate is None:
                    _emit(n)
                else:
                    for e in gate.offer(n):
                        _emit(e)
        if on_window:
            on_window(idx, start, utterances)
    if gate is not None:
        for e in gate.close():
            _emit(e)
    return {"utterances": utterances, "nudges": emitted, "raw_nudges": raw}
