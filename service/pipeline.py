"""업로드 txt → 분석행 + 원문청크 (보고서 1세션 분량).

run_real() : ①전처리 → ③④⑤정제·청킹 → ⑥분석 을 **격리 작업폴더**에서 실제 실행.
             Upstage/LLM API 호출 → 과금·수 분 소요. core/.env 키 필요.

격리 방식: config.SCRIPT_DIR / PROCESSED_DIR / SESSION_SPLIT_HOUR 를 런타임에 작업폴더로
교체(전 파이프라인이 config.X 를 late-binding 참조). 단일강사 모드는 SPLIT_HOUR=24 로 두어
오전/오후 분리를 끄고 '종일' 1세션으로 합친다.

txt 파일명 규약: <date>_<course>.txt  (loader 가 정규식으로 date/course 추출).
"""
from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))

from service.store import Report, _slugify

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _stem(date: str, course: str) -> str:
    return f"{date}_{_slugify(course) or 'lecture'}"


# ══════════════════════════════════════════════════════════════════════
# 실제 파이프라인 (과금)
# ══════════════════════════════════════════════════════════════════════
@contextlib.contextmanager
def _isolated(script_dir: Path, processed_dir: Path, split_hour: int):
    """config 경로/세션분리 임계값을 작업폴더로 일시 교체."""
    from src import config
    saved = (config.SCRIPT_DIR, config.PROCESSED_DIR, config.SESSION_SPLIT_HOUR)
    config.SCRIPT_DIR, config.PROCESSED_DIR, config.SESSION_SPLIT_HOUR = (
        script_dir, processed_dir, split_hour)
    try:
        yield config
    finally:
        config.SCRIPT_DIR, config.PROCESSED_DIR, config.SESSION_SPLIT_HOUR = saved


def _run_main(module_path: str, argv: list[str]) -> None:
    """argparse 기반 러너 main()을 argv 지정해 호출."""
    import importlib
    mod = importlib.import_module(module_path)
    saved_argv = sys.argv
    sys.argv = ["x"] + argv
    try:
        mod.main()
    finally:
        sys.argv = saved_argv


def run_real(raw_text: str, *, date: str, course: str, mode: str,
             self_consistency: int = 3, log=print) -> dict:
    """실제 파이프라인. (date, session) → {"rows":[...], "chunks":[...]}."""
    if not DATE_RE.match(date):
        raise ValueError(f"date 는 YYYY-MM-DD 형식이어야 합니다: {date!r}")
    stem = _stem(date, course)
    work = CORE / "reports" / "_work" / stem
    script_dir, processed = work / "script", work / "processed"
    script_dir.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    (script_dir / f"{stem}.txt").write_text(raw_text, encoding="utf-8")

    split_hour = 24 if mode == "single" else 13
    with _isolated(script_dir, processed, split_hour):
        log("① 전처리 (raw→merged)…")
        _run_main("scripts.run_preprocess", [])
        log("③④⑤ 정제·청킹·태깅 (Upstage, 과금)…")
        _run_main("scripts.run_refine_local", ["--fresh"])
        log(f"⑥ 분석 (self-consistency {self_consistency}, 과금)…")
        _run_main("scripts.run_analyze_local", ["--self-consistency", str(self_consistency)])
        rows = [json.loads(l) for l in (processed / "analysis.jsonl").open(encoding="utf-8") if l.strip()]
        chunks = [json.loads(l) for l in (processed / "chunks.jsonl").open(encoding="utf-8") if l.strip()]

    return _group(rows, chunks, mode)


def _group(rows: list[dict], chunks: list[dict], mode: str) -> dict:
    """행/청크를 (date, session) 으로 묶고, 단일모드면 '종일'로 relabel."""
    def relabel(s):
        return "종일" if mode == "single" else s
    out: dict = {}
    for r in rows:
        s = relabel(r["session"])
        out.setdefault((r["date"], s), {"rows": [], "chunks": []})["rows"].append(r)
    for c in chunks:
        s = relabel(c["session"])
        out.setdefault((c["date"], s), {"rows": [], "chunks": []})["chunks"].append(c)
    return out


# ══════════════════════════════════════════════════════════════════════
# 음성/영상 업로드 → STT 대본 (Gemini, BYO 키)
# ══════════════════════════════════════════════════════════════════════
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
              ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")


def is_media_name(name: str) -> bool:
    return Path(name).suffix.lower() in AUDIO_EXTS


def audio_to_transcript(upload, *, date: str, course: str, start_time: str = None,
                        log=print) -> str:
    """업로드된 오디오/영상 → STT 대본 텍스트(`<HH:MM:SS> 화자ID: text`).

    Gemini 오디오 네이티브 전사(STT_BACKEND=google) — **keymod.applied 안에서 호출**해야
    BYO GOOGLE_API_KEY 가 주입된다. ffmpeg 필요(영상 오디오추출·청크).
    반환 대본은 run_real(raw_text) 에 그대로 넣을 수 있다.
    """
    import tempfile
    from src.stt.model import make_transcribe_fn
    from src.stt.transcribe import transcribe_media

    suffix = Path(upload.name).suffix.lower()
    work = Path(tempfile.mkdtemp(prefix="stt_upload_"))
    src = work / f"input{suffix}"
    src.write_bytes(upload.getvalue())
    tfn = make_transcribe_fn()                       # google(Gemini) — config.STT_BACKEND
    out = transcribe_media(src, date=date, course=course, transcribe_fn=tfn,
                           out_dir=work, work_dir=work / "stt",
                           start_time=start_time, log=log)
    return out.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# 보고서에 반영
# ══════════════════════════════════════════════════════════════════════
def ingest(report: Report, grouped: dict, *, subject: str = "", source_file: str = "",
           added_at: str = "") -> list[tuple[str, str]]:
    """run_real 결과를 보고서에 세션 단위로 저장. 추가된 (date,session) 목록 반환."""
    added = []
    for (date, session), payload in sorted(grouped.items()):
        report.add_session(date=date, session=session, subject=subject,
                           source_file=source_file, rows=payload["rows"],
                           chunks=payload["chunks"], added_at=added_at)
        added.append((date, session))
    return added
