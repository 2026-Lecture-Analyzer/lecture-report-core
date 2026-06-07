"""Step 2 — 화자 매핑 + 발화 병합 (규칙 기반, 모델 미사용).

(2a) 화자 매핑: **파일(일자) 단위**로 speaker_id 별 발화량을 집계해
     최다 발화자=강사, 나머지=학생N. 해시 ID가 세션마다 바뀌므로 전역이 아닌
     파일별 매핑. 결과는 speaker_map.json 으로 저장 → 사람이 수동 보정 가능.
     발화량 동률 시에는 강사 판정이 모호하므로 경고를 남긴다(수동 확인 유도).

(2b) 발화 병합: 같은 화자의 연속 발화를 시간 간격 임계값(config.MERGE_GAP_SEC)
     이내로 한 블록으로 합침. "한 문장이 여러 타임스탬프로 쪼개진" 문제 해결.
     블록이 너무 커지지 않도록 시간/글자 상한(config) 적용.

     [개선] 미완성 어미 감지: 발화가 ~고/~서/~면/~는데/~니까 등 접속 어미로
     끝나면 시간 간격과 무관하게 다음 발화와 강제 병합한다.
     단, max_block_sec / max_block_chars 상한은 여전히 적용해 블록이 무한정
     커지는 것을 막는다.

merged 블록 스키마:
    {block_id, file, date, session, speaker_id, speaker_role,
     start_time, end_time, start_sec, end_sec, dur_sec, n_utts,
     text, raw_ref:[idx,...]}
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Final

from src import config

# ── jch: 로거 + 화자 역할 상수 ────────────────────────────────────────────
logger: logging.Logger = logging.getLogger(__name__)

ROLE_INSTRUCTOR: Final[str] = "강사"
ROLE_STUDENT_PREFIX: Final[str] = "학생"
ROLE_UNKNOWN: Final[str] = "미상"

# ── ljs: 미완성 어미 패턴 ─────────────────────────────────────────────────
# 발화 끝이 아래 패턴과 일치하면 문장이 아직 끝나지 않은 것으로 판단한다.
# 패턴 설명:
#   ~고, ~고요          → "읽고", "열고요"
#   ~서, ~서요          → "해서", "있어서요"
#   ~면, ~면서          → "하면", "되면서"
#   ~는데, ~은데, ~ㄴ데 → "하는데", "있는데"
#   ~니까, ~니깐        → "하니까"
#   ~지만               → "하지만"
#   ~거나               → "하거나"
#   ~(으)면서           → "하면서"
#   ~도록               → "하도록"
#   ~어서, ~아서        → "나와서", "가져와서"
# 줄 끝($)에 이 패턴이 있으면 미완성으로 본다.
_INCOMPLETE_RE = re.compile(
    r"(고요?|서요?|면서?|는데|은데|ㄴ데|니까|니깐|지만|거나|도록|어서|아서)\s*$"
)


def is_incomplete(text: str) -> bool:
    """발화가 미완성 어미로 끝나는지 확인."""
    return bool(_INCOMPLETE_RE.search(text.strip()))


def load_raw(raw_path: Path) -> list[dict]:
    """raw.jsonl 을 레코드 dict 리스트로 읽는다."""
    with Path(raw_path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_speaker_map(records: list[dict]) -> dict[str, dict[str, str]]:
    """파일별 speaker_id → 역할(강사/학생N) 매핑.

    발화량 최다 = 강사, 그다음부터 발화량 순으로 학생1, 학생2 ...
    동률은 speaker_id 오름차순으로 안정 정렬해 재현성을 보장한다.
    """
    per_file: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        if r.get("malformed") or not r.get("speaker_id"):
            continue
        per_file[r["file"]][r["speaker_id"]] += 1

    mapping: dict[str, dict[str, str]] = {}
    for file, counter in per_file.items():
        # 발화량 내림차순, 동률은 speaker_id 오름차순(안정·재현 가능)
        ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        if len(ranked) >= 2 and ranked[0][1] == ranked[1][1]:
            logger.warning(
                "화자 매핑 모호: %s — 최다 발화 동률(%d건). "
                "speaker_map.json 수동 확인 권장",
                file, ranked[0][1],
            )
        role: dict[str, str] = {}
        for i, (sid, _count) in enumerate(ranked):
            role[sid] = ROLE_INSTRUCTOR if i == 0 else f"{ROLE_STUDENT_PREFIX}{i}"
        mapping[file] = role
    logger.debug("화자 매핑 완료: %d개 파일", len(mapping))
    return mapping


def merge_utterances(
    records: list[dict],
    speaker_map: dict[str, dict[str, str]],
    gap_sec: float | None = None,
    max_block_sec: float | None = None,
    max_block_chars: int | None = None,
) -> list[dict]:
    """연속 동일화자 발화를 블록으로 병합.

    기존 조건(시간 간격, 상한) 외에 미완성 어미 감지를 추가한다.
    현재 블록의 마지막 발화가 미완성 어미로 끝나면 gap_sec 초과여도
    같은 화자의 다음 발화를 강제로 이어 붙인다.
    단, max_block_sec / max_block_chars 상한은 미완성 어미 상황에서도 유지한다.
    """
    gap_sec = config.MERGE_GAP_SEC if gap_sec is None else gap_sec
    max_block_sec = config.MERGE_MAX_BLOCK_SEC if max_block_sec is None else max_block_sec
    max_block_chars = config.MERGE_MAX_BLOCK_CHARS if max_block_chars is None else max_block_chars

    blocks: list[dict] = []
    cur: dict | None = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            cur["text"] = " ".join(cur["_texts"]).strip()
            cur["n_utts"] = len(cur["raw_ref"])
            del cur["_texts"]
            del cur["_chars"]
            cur["block_id"] = len(blocks)
            blocks.append(cur)
            cur = None

    for r in records:
        if r.get("malformed") or r.get("sec_of_day") is None:
            flush()  # 정형 이탈 줄은 경계로 처리
            continue
        role = speaker_map.get(r["file"], {}).get(r["speaker_id"], ROLE_UNKNOWN)
        sec = r["sec_of_day"]
        text_len = len(r["text"])

        # 상한 초과 여부 (미완성 어미여도 이건 강제 분리) — ljs 구조, over_chars는 jch _chars 최적화 적용
        over_time = cur is not None and (sec - cur["start_sec"]) > max_block_sec
        over_chars = cur is not None and (cur["_chars"] + text_len) > max_block_chars

        # 현재 블록의 마지막 발화가 미완성 어미로 끝나는지 — ljs 도메인 로직
        cur_incomplete = (
            cur is not None
            and cur["speaker_id"] == r["speaker_id"]
            and cur["file"] == r["file"]
            and is_incomplete(cur["_texts"][-1])
            and not over_time
            and not over_chars
        )

        # 기본 new_turn 판단
        new_turn = (
            cur is None
            or cur["file"] != r["file"]
            or cur["speaker_id"] != r["speaker_id"]
            or (sec - cur["end_sec"]) > gap_sec
            or over_time
            or over_chars
        )

        # 미완성 어미면 new_turn 을 덮어써서 강제 병합 — ljs 도메인 로직
        if cur_incomplete:
            new_turn = False

        if new_turn:
            flush()
            cur = dict(
                file=r["file"], date=r["date"], session=r["session"],
                speaker_id=r["speaker_id"], speaker_role=role,
                start_time=r["time"], end_time=r["time"],
                start_sec=sec, end_sec=sec,
                _texts=[r["text"]], raw_ref=[r["idx"]], _chars=text_len,
            )
        else:
            cur["_texts"].append(r["text"])
            cur["raw_ref"].append(r["idx"])
            cur["end_time"] = r["time"]
            cur["end_sec"] = sec
            cur["_chars"] += text_len
    flush()

    logger.debug("발화 병합 완료: 블록 %d개", len(blocks))
    for b in blocks:
        b["dur_sec"] = b["end_sec"] - b["start_sec"]
    cols = ["block_id", "file", "date", "session", "speaker_id", "speaker_role",
            "start_time", "end_time", "start_sec", "end_sec", "dur_sec",
            "n_utts", "text", "raw_ref"]
    return [{k: b[k] for k in cols} for b in blocks]


def run_step2(
    raw_path: Path,
    out_dir: Path,
    gap_sec: float | None = None,
    max_block_sec: float | None = None,
    max_block_chars: int | None = None,
) -> dict[str, int | str]:
    """raw.jsonl → speaker_map.json + merged.jsonl 생성."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("run_step2 시작: raw=%s, out=%s", raw_path, out_dir)
    records = load_raw(raw_path)

    smap = build_speaker_map(records)
    smap_path = out_dir / "speaker_map.json"
    smap_path.write_text(json.dumps(smap, ensure_ascii=False, indent=2), encoding="utf-8")

    blocks = merge_utterances(
        records, smap,
        gap_sec=gap_sec, max_block_sec=max_block_sec, max_block_chars=max_block_chars,
    )
    merged_path = out_dir / "merged.jsonl"
    with merged_path.open("w", encoding="utf-8") as w:
        for b in blocks:
            w.write(json.dumps(b, ensure_ascii=False) + "\n")

    logger.debug("run_step2 완료: 블록 %d개", len(blocks))
    return {
        "blocks": len(blocks),
        "input_records": len(records),
        "speaker_map": str(smap_path),
        "merged": str(merged_path),
    }
