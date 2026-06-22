"""Step 4 전처리 — 병합 블록을 '큰 섹션'으로 묶기 (순수 로직, 모델 미사용).

정제(Step 4)는 문장 단위가 아니라 **큰 섹션 단위**로 모델에 넣는다(맥락 보존).
같은 파일·세션 내에서 인접 블록을 SECTION_MAX_CHARS 한도까지 누적해 섹션을 만든다.
원본 추적성 유지를 위해 block_ids / raw_ref 를 끝까지 들고 간다.

[개선] 오버랩 윈도우:
    make_sections_with_overlap() 을 사용하면 각 섹션의 앞뒤에 이웃 섹션의
    블록을 overlap_blocks 개수만큼 포함시킨다.
    포함된 이웃 블록에는 ctx=True 플래그가 붙어, render_section() 이
    [CTX] 태그로 감싸 모델에 전달한다.
    모델은 [CTX] 블록은 맥락 파악에만 쓰고 [MAIN] 블록만 출력한다.
    → 섹션 경계에 걸쳐 있는 문장을 자연스럽게 완성할 수 있다.

섹션 스키마:
    {section_id, file, date, session, block_ids, raw_ref,
     start_time, end_time, start_sec, end_sec, n_chars,
     blocks:[{speaker_role, text, ctx}]}
     (ctx=True 인 블록은 오버랩용 맥락 블록)
"""
from __future__ import annotations

import json
from pathlib import Path

from src import config


def load_merged(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def make_sections(blocks: list[dict], max_chars: int | None = None) -> list[dict]:
    """기존 방식 — 오버랩 없이 섹션을 딱 잘라 나눈다."""
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
        cur["blocks"].append({"speaker_role": b["speaker_role"], "text": b["text"], "ctx": False})
        cur["end_time"] = b["end_time"]
        cur["end_sec"] = b["end_sec"]
        cur["n_chars"] += len(b["text"])
    flush()
    return sections


def make_sections_with_overlap(
    blocks: list[dict],
    max_chars: int | None = None,
    overlap_blocks: int = 2,
) -> list[dict]:
    """오버랩 윈도우 방식 — 섹션 경계 앞뒤로 블록을 맥락용으로 포함.

    1단계: make_sections() 로 섹션을 먼저 딱 잘라 만든다.
    2단계: 각 섹션에 이전 섹션의 마지막 overlap_blocks 개 블록을 [CTX] 앞에,
           다음 섹션의 첫 overlap_blocks 개 블록을 [CTX] 뒤에 붙인다.
           단, 파일/세션이 다른 경우에는 붙이지 않는다.

    ctx=True 블록은 block_ids / raw_ref 에 포함하지 않는다.
    (추적성은 MAIN 블록 기준으로만 유지)
    """
    # 1단계: 기본 섹션 생성
    base_sections = make_sections(blocks, max_chars)
    if not base_sections:
        return base_sections

    # block_id → block 빠른 조회용
    block_by_id: dict[int, dict] = {b["block_id"]: b for b in blocks}

    result = []
    for i, sec in enumerate(base_sections):
        # 이 섹션의 MAIN 블록 목록 (ctx=False)
        main_blocks = [blk for blk in sec["blocks"] if not blk.get("ctx")]

        # ── 앞 CTX: 이전 섹션의 마지막 N개 블록 ──
        prev_ctx: list[dict] = []
        if i > 0:
            prev_sec = base_sections[i - 1]
            # 파일·세션이 같을 때만 붙인다
            if prev_sec["file"] == sec["file"] and prev_sec["session"] == sec["session"]:
                prev_main_ids = [
                    bid for bid in prev_sec["block_ids"]
                ]
                for bid in prev_main_ids[-overlap_blocks:]:
                    b = block_by_id.get(bid)
                    if b:
                        prev_ctx.append({
                            "speaker_role": b["speaker_role"],
                            "text": b["text"],
                            "ctx": True,
                        })

        # ── 뒤 CTX: 다음 섹션의 첫 N개 블록 ──
        next_ctx: list[dict] = []
        if i < len(base_sections) - 1:
            next_sec = base_sections[i + 1]
            if next_sec["file"] == sec["file"] and next_sec["session"] == sec["session"]:
                next_main_ids = [
                    bid for bid in next_sec["block_ids"]
                ]
                for bid in next_main_ids[:overlap_blocks]:
                    b = block_by_id.get(bid)
                    if b:
                        next_ctx.append({
                            "speaker_role": b["speaker_role"],
                            "text": b["text"],
                            "ctx": True,
                        })

        new_sec = dict(
            section_id=sec["section_id"],
            file=sec["file"],
            date=sec["date"],
            session=sec["session"],
            block_ids=sec["block_ids"],          # MAIN 블록 id만
            raw_ref=sec["raw_ref"],              # MAIN 블록 raw_ref만
            start_time=sec["start_time"],
            end_time=sec["end_time"],
            start_sec=sec["start_sec"],
            end_sec=sec["end_sec"],
            n_chars=sec["n_chars"],
            blocks=prev_ctx + main_blocks + next_ctx,
        )
        result.append(new_sec)

    return result


def render_section(section: dict) -> str:
    """모델 입력용 텍스트.

    ctx=True 블록은 [CTX] 태그로, 그 외는 [MAIN] 태그로 감싼다.
    오버랩 없이 make_sections() 로 만든 섹션(ctx 키 없음)도 그대로 동작한다.
    """
    lines = []
    for blk in section["blocks"]:
        if blk.get("ctx"):
            lines.append(f"[CTX][{blk['speaker_role']}] {blk['text']}")
        else:
            lines.append(f"[MAIN][{blk['speaker_role']}] {blk['text']}")
    return "\n".join(lines)
