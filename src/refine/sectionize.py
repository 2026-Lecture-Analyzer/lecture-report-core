"""Step 4 전처리 — 병합 블록을 '큰 섹션'으로 묶기 (순수 로직, 모델 미사용).

정제(Step 4)는 문장 단위가 아니라 **큰 섹션 단위**로 모델에 넣는다(맥락 보존).
같은 파일·세션 내에서 인접 블록을 SECTION_MAX_CHARS 한도까지 누적해 섹션을 만든다.
원본 추적성 유지를 위해 block_ids / raw_ref 를 끝까지 들고 간다.

섹션 스키마:
    {section_id, file, date, session, block_ids, raw_ref,
     start_time, end_time, start_sec, end_sec, n_chars,
     blocks:[{speaker_role, text}]}
"""
from __future__ import annotations

import json
from pathlib import Path

from src import config


def load_merged(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def make_sections(blocks: list[dict], max_chars: int | None = None) -> list[dict]:
    max_chars = config.SECTION_MAX_CHARS if max_chars is None else max_chars
    sections: list[dict] = []
    cur: dict | None = None

    def flush():
        nonlocal cur
        if cur is not None:
            cur["section_id"] = len(sections)
            sections.append(cur)
            cur = None

    for b in blocks:
        same_ctx = (
            cur is not None
            and cur["file"] == b["file"]
            and cur["session"] == b["session"]
        )
        fits = cur is not None and (cur["n_chars"] + len(b["text"])) <= max_chars
        if not (same_ctx and fits):
            flush()
            cur = dict(
                file=b["file"], date=b["date"], session=b["session"],
                block_ids=[], raw_ref=[], blocks=[],
                start_time=b["start_time"], end_time=b["end_time"],
                start_sec=b["start_sec"], end_sec=b["end_sec"], n_chars=0,
            )
        cur["block_ids"].append(b["block_id"])
        cur["raw_ref"].extend(b["raw_ref"])
        cur["blocks"].append({"speaker_role": b["speaker_role"], "text": b["text"]})
        cur["end_time"] = b["end_time"]
        cur["end_sec"] = b["end_sec"]
        cur["n_chars"] += len(b["text"])
    flush()
    return sections


def render_section(section: dict) -> str:
    """모델 입력용 텍스트. 화자 역할 태그를 붙여 강사/학생 발화를 구분."""
    lines = []
    for blk in section["blocks"]:
        lines.append(f"[{blk['speaker_role']}] {blk['text']}")
    return "\n".join(lines)
