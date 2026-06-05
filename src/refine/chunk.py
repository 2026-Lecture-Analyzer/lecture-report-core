"""Step 5 — 주제 단위 청킹 (모델 호출, generate_fn 주입).

정제된 섹션(clean.jsonl)을 주제 단위로 재분할한다. 모델이 clean_text 를
직접 자르므로 청크별 정확한 raw_ref 는 알 수 없어, **부모 섹션의 시간범위·raw_ref
를 상속**해 추적성을 유지한다(v1). 향후 정렬 기반 매핑으로 정밀화 가능.

체크포인트: 섹션 단위로 처리 완료를 기록(처리된 section_id 의 청크는 재생성 안 함).

chunk 레코드 스키마:
    {chunk_id, section_id, file, date, session, topic, clean_text,
     raw_ref, start_time, end_time}
"""
from __future__ import annotations

import json
from pathlib import Path

from src.refine.jsonout import extract_json
from src.refine.prompts import chunk_prompt


def _load_clean(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _done_sections(out_path: Path) -> set:
    p = Path(out_path)
    if not p.exists():
        return set()
    done = set()
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                done.add(json.loads(line)["section_id"])
    return done


def run_chunk(clean_path: Path, generate_fn, out_path: Path, log=print) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clean = _load_clean(clean_path)
    done = _done_sections(out_path)
    if done:
        log(f"[resume] 청킹 완료된 섹션 {len(done)}개 건너뜀")

    # 다음 chunk_id 시작값
    next_id = 0
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            next_id = sum(1 for line in f if line.strip())

    n_chunks = 0
    with out_path.open("a", encoding="utf-8") as w:
        for rec in clean:
            if rec["section_id"] in done:
                continue
            out = generate_fn(chunk_prompt(rec["clean_text"]))
            data = extract_json(out) or {}
            chunks = data.get("chunks") or [{"topic": "", "text": rec["clean_text"]}]
            for ch in chunks:
                text = (ch.get("text") or "").strip()
                if not text:
                    continue
                w.write(json.dumps({
                    "chunk_id": next_id, "section_id": rec["section_id"],
                    "file": rec["file"], "date": rec["date"], "session": rec["session"],
                    "topic": (ch.get("topic") or "").strip(),
                    "clean_text": text, "raw_ref": rec["raw_ref"],
                    "start_time": rec["start_time"], "end_time": rec["end_time"],
                }, ensure_ascii=False) + "\n")
                next_id += 1
                n_chunks += 1
            w.flush()

    return {"chunks": n_chunks, "sections_processed": len(clean) - len(done),
            "output": str(out_path)}
