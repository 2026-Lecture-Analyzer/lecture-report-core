"""Step 5 (임베딩판) — clean.jsonl → chunks.jsonl + eval_tags.

문헌(TreeSeg/TextTiling) 근거로 LLM 청킹 대신 **임베딩 기반 토픽 분할**을 메인으로.
한 강의(date_session)를 문장열로 펴서 임베딩 1회 → (a) 토픽 경계 분할 (b) 평가항목 태깅
두 가지에 **같은 임베딩을 공유**(folding) → 추가 호출 0. (§9, §11)

원본 추적성: 각 문장이 어느 section/raw_ref/time 에서 왔는지 들고 다니다 chunk로 합침.

chunks.jsonl 스키마(확장):
    {chunk_id, lecture_id, file, date, session, pos,
     clean_text, raw_ref, start_time, end_time,
     eval_tags:[{item_key, sim, cue}]}
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from src.refine.segment import segment_sentences, split_sentences
from src.refine.tagging import tag_chunks


def _load_clean(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _lecture_sentences(sections: list[dict]) -> list[dict]:
    """강의의 섹션들 → 문장 단위 레코드(출처 메타 보존)."""
    sents = []
    for sec in sections:
        for s in split_sentences(sec.get("clean_text", "")):
            sents.append({"text": s, "section_id": sec["section_id"],
                          "raw_ref": sec.get("raw_ref", []),
                          "start_time": sec.get("start_time"),
                          "end_time": sec.get("end_time")})
    return sents


def chunk_and_tag_lecture(lecture_id: str, sections: list[dict], embed_fn,
                          next_id: int) -> list[dict]:
    meta = sections[0]
    sents = _lecture_sentences(sections)
    if not sents:
        return []
    texts = [s["text"] for s in sents]
    emb = embed_fn(texts)                                  # 문장 임베딩 1회
    groups = segment_sentences(texts, emb=emb)             # 분할(공유)

    chunks = []
    for gi, g in enumerate(groups):
        raw_ref = sorted({r for i in g for r in sents[i]["raw_ref"]})
        chunk_emb = emb[g].mean(axis=0)                    # 태깅용(공유)
        chunks.append({
            "chunk_id": next_id + gi, "lecture_id": lecture_id,
            "file": meta["file"], "date": meta["date"], "session": meta["session"],
            "pos": (gi + 0.5) / len(groups),
            "clean_text": " ".join(texts[i] for i in g),
            "raw_ref": raw_ref,
            "start_time": sents[g[0]]["start_time"],
            "end_time": sents[g[-1]]["end_time"],
            "chunk_emb": chunk_emb,
        })
    tag_chunks(chunks, embed_fn)                           # eval_tags 부착(같은 임베딩 재사용)
    for c in chunks:                                       # 직렬화 불가 임베딩 제거
        c.pop("chunk_emb", None)
    return chunks


def run_chunk_embed(clean_path: Path, embed_fn, out_path: Path, log=print) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clean = _load_clean(clean_path)
    lectures: dict[str, list[dict]] = defaultdict(list)
    for r in clean:
        lectures[f"{r['date']}_{r['session']}"].append(r)

    n_chunks = 0
    with out_path.open("w", encoding="utf-8") as w:
        for lid, secs in lectures.items():
            secs.sort(key=lambda s: s["section_id"])
            chunks = chunk_and_tag_lecture(lid, secs, embed_fn, n_chunks)
            for c in chunks:
                w.write(json.dumps(c, ensure_ascii=False) + "\n")
            n_chunks += len(chunks)
            log(f"  {lid}: {len(chunks)} chunks")
    return {"lectures": len(lectures), "chunks": n_chunks, "output": str(out_path)}
