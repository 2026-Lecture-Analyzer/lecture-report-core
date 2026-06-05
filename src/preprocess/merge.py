"""Step 2 — 화자 매핑 + 발화 병합 (규칙 기반, 모델 미사용).

(2a) 화자 매핑: **파일(일자) 단위**로 speaker_id 별 발화량을 집계해
     최다 발화자=강사, 나머지=학생N. 해시 ID가 세션마다 바뀌므로 전역이 아닌
     파일별 매핑. 결과는 speaker_map.json 으로 저장 → 사람이 수동 보정 가능.

(2b) 발화 병합: 같은 화자의 연속 발화를 시간 간격 임계값(config.MERGE_GAP_SEC)
     이내로 한 블록으로 합침. "한 문장이 여러 타임스탬프로 쪼개진" 문제 해결.
     블록이 너무 커지지 않도록 시간/글자 상한(config) 적용.

merged 블록 스키마:
    {block_id, file, date, session, speaker_id, speaker_role,
     start_time, end_time, start_sec, end_sec, dur_sec, n_utts,
     text, raw_ref:[idx,...]}
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from src import config


def load_raw(raw_path: Path) -> list[dict]:
    with Path(raw_path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_speaker_map(records: list[dict]) -> dict[str, dict[str, str]]:
    """파일별 speaker_id → 역할(강사/학생N) 매핑.

    발화량 최다 = 강사, 그다음부터 발화량 순으로 학생1, 학생2 ...
    """
    per_file: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        if r.get("malformed") or not r.get("speaker_id"):
            continue
        per_file[r["file"]][r["speaker_id"]] += 1

    mapping: dict[str, dict[str, str]] = {}
    for file, counter in per_file.items():
        ranked = [sid for sid, _ in counter.most_common()]
        role = {}
        for i, sid in enumerate(ranked):
            role[sid] = "강사" if i == 0 else f"학생{i}"
        mapping[file] = role
    return mapping


def merge_utterances(
    records: list[dict],
    speaker_map: dict[str, dict[str, str]],
    gap_sec: float | None = None,
    max_block_sec: float | None = None,
    max_block_chars: int | None = None,
) -> list[dict]:
    """연속 동일화자 발화를 블록으로 병합."""
    gap_sec = config.MERGE_GAP_SEC if gap_sec is None else gap_sec
    max_block_sec = config.MERGE_MAX_BLOCK_SEC if max_block_sec is None else max_block_sec
    max_block_chars = config.MERGE_MAX_BLOCK_CHARS if max_block_chars is None else max_block_chars

    blocks: list[dict] = []
    cur: dict | None = None

    def flush():
        nonlocal cur
        if cur is not None:
            cur["text"] = " ".join(cur["_texts"]).strip()
            cur["n_utts"] = len(cur["raw_ref"])
            del cur["_texts"]
            cur["block_id"] = len(blocks)
            blocks.append(cur)
            cur = None

    for r in records:
        if r.get("malformed") or r.get("sec_of_day") is None:
            flush()  # 정형 이탈 줄은 경계로 처리
            continue
        role = speaker_map.get(r["file"], {}).get(r["speaker_id"], "미상")
        sec = r["sec_of_day"]

        new_turn = (
            cur is None
            or cur["file"] != r["file"]
            or cur["speaker_id"] != r["speaker_id"]
            or (sec - cur["end_sec"]) > gap_sec
            or (sec - cur["start_sec"]) > max_block_sec
            or (sum(len(t) for t in cur["_texts"]) + len(r["text"])) > max_block_chars
        )
        if new_turn:
            flush()
            cur = dict(
                file=r["file"], date=r["date"], session=r["session"],
                speaker_id=r["speaker_id"], speaker_role=role,
                start_time=r["time"], end_time=r["time"],
                start_sec=sec, end_sec=sec,
                _texts=[r["text"]], raw_ref=[r["idx"]],
            )
        else:
            cur["_texts"].append(r["text"])
            cur["raw_ref"].append(r["idx"])
            cur["end_time"] = r["time"]
            cur["end_sec"] = sec
    flush()

    for b in blocks:
        b["dur_sec"] = b["end_sec"] - b["start_sec"]
    # 키 순서 정리
    cols = ["block_id", "file", "date", "session", "speaker_id", "speaker_role",
            "start_time", "end_time", "start_sec", "end_sec", "dur_sec",
            "n_utts", "text", "raw_ref"]
    return [{k: b[k] for k in cols} for b in blocks]


def run_step2(raw_path: Path, out_dir: Path, **merge_kwargs) -> dict:
    """raw.jsonl → speaker_map.json + merged.jsonl 생성."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = load_raw(raw_path)

    smap = build_speaker_map(records)
    smap_path = out_dir / "speaker_map.json"
    smap_path.write_text(json.dumps(smap, ensure_ascii=False, indent=2), encoding="utf-8")

    blocks = merge_utterances(records, smap, **merge_kwargs)
    merged_path = out_dir / "merged.jsonl"
    with merged_path.open("w", encoding="utf-8") as w:
        for b in blocks:
            w.write(json.dumps(b, ensure_ascii=False) + "\n")

    return {
        "blocks": len(blocks),
        "input_records": len(records),
        "speaker_map": str(smap_path),
        "merged": str(merged_path),
    }
