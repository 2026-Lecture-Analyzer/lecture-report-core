"""Step 1 — 파싱 (규칙 기반, 모델 미사용).

STT txt 한 줄 `<HH:MM:SS> speaker_id: text` 을 발화 레코드로 분해해 raw.jsonl 로 저장.
- 메타데이터(subject 등)는 **결합하지 않는다** (내용-메타 불일치 이슈 때문).
- 타임스탬프는 12시간제 → 24시간제로 보정(loader.to_24h 재사용).
- 원본 불변 원칙: text 는 가공하지 않고 그대로 보존, 전역 idx 로 추적성 부여.

raw 레코드 스키마:
    {idx, file, date, course_id, line_no, time, sec_of_day, hour, session,
     speaker_id, text}
"""
from __future__ import annotations

import json
from pathlib import Path

from src import config
from src.preprocess.loader import _FNAME_RE, _LINE_RE, _session_from_hour24, to_24h


def iter_raw_records(script_dir: Path | None = None):
    """모든 STT 파일을 발화 단위 dict 로 순회한다(전역 idx 부여)."""
    script_dir = Path(script_dir or config.SCRIPT_DIR)
    files = sorted(script_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(
            f"강의 스크립트를 찾을 수 없음: {script_dir} (제공 데이터는 git 미포함)"
        )
    idx = 0
    for path in files:
        fm = _FNAME_RE.match(path.name)
        if not fm:
            raise ValueError(f"예상치 못한 파일명: {path.name}")
        date, course_id = fm.group(1), fm.group(2)
        with path.open(encoding="utf-8") as f:
            for line_no, raw in enumerate(f, start=1):
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                lm = _LINE_RE.match(line)
                if not lm:
                    # 정형 이탈 줄도 추적 가능하도록 보존(malformed)
                    yield dict(idx=idx, file=path.name, date=date,
                               course_id=course_id, line_no=line_no, time=None,
                               sec_of_day=None, hour=None, session=None,
                               speaker_id=None, text=line, malformed=True)
                    idx += 1
                    continue
                hh, mm, ss = int(lm.group(1)), int(lm.group(2)), int(lm.group(3))
                h24 = to_24h(hh)
                yield dict(
                    idx=idx, file=path.name, date=date, course_id=course_id,
                    line_no=line_no, time=f"{h24:02d}:{mm:02d}:{ss:02d}",
                    sec_of_day=h24 * 3600 + mm * 60 + ss, hour=h24,
                    session=_session_from_hour24(h24),
                    speaker_id=lm.group(4), text=lm.group(5).strip(),
                    malformed=False,
                )
                idx += 1


def write_raw_jsonl(out_path: Path, script_dir: Path | None = None) -> dict:
    """raw.jsonl 생성. 반환: 간단 통계(행수, 파일수, malformed수)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n, n_malformed, files = 0, 0, set()
    with out_path.open("w", encoding="utf-8") as w:
        for rec in iter_raw_records(script_dir):
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            n_malformed += int(rec["malformed"])
            files.add(rec["file"])
    return {"records": n, "files": len(files), "malformed": n_malformed,
            "output": str(out_path)}
