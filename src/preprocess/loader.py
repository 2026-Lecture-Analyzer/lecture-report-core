"""STT 강의 스크립트 + 메타데이터를 구조화된 DataFrame으로 적재.

핵심 산출물:
- `load_utterances()`  : 발화 1건 = 1행 (장기적으로 모든 분석의 기본 단위)
- `load_metadata()`    : (날짜, 세션) 단위 강의 메타데이터
- `build_dataset()`    : 위 둘을 결합한 분석용 테이블

STT 한 줄 형식:  `<HH:MM:SS> 화자ID: 발화내용`
파일명 형식:      `YYYY-MM-DD_<course_id>.txt`
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src import config

# `<09:11:17> b54f46b0: 텍스트` 한 줄 파서
_LINE_RE = re.compile(r"^<(\d{2}):(\d{2}):(\d{2})>\s+([0-9a-fA-F]+):\s?(.*)$")
_FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)\.txt$")


def to_24h(hour: int) -> int:
    """STT 타임스탬프는 12시간제(AM/PM 미표기)다.

    실제 강의는 09:00~18:00 이므로:
      - 09,10,11,12시 → 오전/정오 그대로
      - 01~05시       → 오후(13~17시)로 보정 (+12)
    """
    return hour + 12 if 1 <= hour <= 6 else hour


def _session_from_hour24(hour24: int) -> str:
    return "오전" if hour24 < config.SESSION_SPLIT_HOUR else "오후"


def parse_script_file(path: Path) -> pd.DataFrame:
    """단일 STT 파일을 발화 단위 DataFrame으로 파싱한다."""
    m = _FNAME_RE.match(path.name)
    if not m:
        raise ValueError(f"예상치 못한 파일명 형식: {path.name}")
    date, course_id = m.group(1), m.group(2)

    rows = []
    with path.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            lm = _LINE_RE.match(line)
            if not lm:
                # 정형에서 벗어난 줄은 버리지 않고 기록 → EDA에서 품질 점검
                rows.append(
                    dict(date=date, course_id=course_id, lineno=lineno,
                         timestamp=None, hour=None, minute_of_day=None,
                         session=None, speaker=None, text=line, malformed=True)
                )
                continue
            hh, mm, ss, speaker, text = (
                int(lm.group(1)), int(lm.group(2)), int(lm.group(3)),
                lm.group(4), lm.group(5).strip(),
            )
            hour24 = to_24h(hh)
            rows.append(dict(
                date=date, course_id=course_id, lineno=lineno,
                timestamp=f"{hour24:02d}:{mm:02d}:{ss:02d}", hour=hour24,
                minute_of_day=hour24 * 60 + mm,
                session=_session_from_hour24(hour24), speaker=speaker,
                text=text, malformed=False,
            ))
    return pd.DataFrame(rows)


def load_utterances(script_dir: Path | None = None) -> pd.DataFrame:
    """모든 STT 파일을 합쳐 발화 단위 DataFrame을 만든다."""
    script_dir = script_dir or config.SCRIPT_DIR
    files = sorted(Path(script_dir).glob("*.txt"))
    if not files:
        raise FileNotFoundError(
            f"강의 스크립트를 찾을 수 없음: {script_dir}\n"
            "→ 제공 데이터는 git에 포함되지 않습니다. 로컬에 원본을 배치하세요."
        )
    df = pd.concat([parse_script_file(p) for p in files], ignore_index=True)
    df["char_len"] = df["text"].str.len()
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_metadata(csv_path: Path | None = None) -> pd.DataFrame:
    """강의 메타데이터 CSV → (날짜, 세션) 단위 테이블."""
    csv_path = csv_path or config.METADATA_CSV
    # BOM 포함 UTF-8 → utf-8-sig
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    # 'time' = "09:00 ~ 12:00" → 시작 시각으로 세션 판정 (메타는 24시간제)
    start_hour = df["time"].str.extract(r"^(\d{2}):").astype(int)[0]
    df["session"] = start_hour.apply(_session_from_hour24)
    return df


def build_dataset(
    script_dir: Path | None = None, csv_path: Path | None = None
) -> pd.DataFrame:
    """발화 + 메타데이터를 (date, session) 키로 결합한 분석용 테이블."""
    utt = load_utterances(script_dir)
    meta = load_metadata(csv_path)
    meta_cols = ["date", "session", "subject", "content", "instructor", "sub_instructor"]
    merged = utt.merge(meta[meta_cols], on=["date", "session"], how="left")
    return merged
