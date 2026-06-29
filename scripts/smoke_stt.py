"""STT 배관 스모크 — 모델/ffmpeg/오디오 없이 조립 로직을 검증.

핵심 보증: STT 가 만든 transcript 라인이 기존 parse_line(loader) 으로 **그대로 파싱**되는가
(포맷 계약). + 청크 오프셋·겹침 중복제거·세그먼트 파서 동작.

사용: python -m scripts.smoke_stt
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.preprocess.loader import parse_line  # noqa: E402
from src.stt import audio as A  # noqa: E402
from src.stt.prompts import parse_segments  # noqa: E402
from src.stt.transcribe import assemble_lines, fmt_ts, start_seconds  # noqa: E402


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"  ✓ {msg}")


def test_parse_segments():
    print("· parse_segments(지저분한 모델 출력)")
    raw = """좋아요, 전사 결과입니다:
```json
[{"t": 0.0, "spk": 0, "text": "안녕하세요 시작하겠습니다"},
 {"t": 3.5, "spk": 1, "text": "네"},
 {"t": 2.0, "spk": 0, "text": "오늘은 입출력입니다"},
 {"t": 9.9, "spk": 0, "text": "   "}]
```"""
    segs = parse_segments(raw)
    _check(len(segs) == 3, f"빈 text 제외하고 3개 (got {len(segs)})")
    _check(segs[0]["t"] <= segs[1]["t"] <= segs[2]["t"], "t 기준 정렬됨")
    _check(all(isinstance(s["spk"], int) for s in segs), "spk 정수화")


def test_plan_chunks():
    print("· plan_chunks(겹침 경계)")
    chunks = A.plan_chunks(1300, chunk_sec=600, overlap_sec=5)
    _check(len(chunks) == 3, f"1300s/600s → 3청크 (got {len(chunks)})")
    _check(chunks[0].start_sec == 0.0, "0번 청크는 0초 시작(겹침 없음)")
    _check(abs(chunks[1].start_sec - 595.0) < 1e-6, "1번 청크는 595초 시작(600-5 겹침)")
    one = A.plan_chunks(120, chunk_sec=600, overlap_sec=5)
    _check(len(one) == 1, "짧으면 통째 1청크")


def test_assemble_roundtrip():
    print("· assemble_lines → parse_line 라운드트립(포맷 계약)")
    chunks = A.plan_chunks(1300, chunk_sec=600, overlap_sec=5)
    # 청크별 상대 세그먼트: 1번 청크 앞 5초(겹침)는 0번 꼬리와 중복 → 제거되어야
    per_chunk = [
        [{"t": 0.0, "spk": 0, "text": "안녕하세요"},
         {"t": 597.0, "spk": 0, "text": "여기는 0번 청크 꼬리"}],
        [{"t": 2.0, "spk": 0, "text": "겹침구간-중복이라 버려져야"},   # 상대 2초 < overlap 5
         {"t": 10.0, "spk": 1, "text": "학생 질문입니다"}],
        [{"t": 10.0, "spk": 0, "text": "마지막 청크 발화"}],          # 겹침(5초) 밖이라 유지
    ]
    lines = assemble_lines(per_chunk, chunks, start_time="09:00:00", overlap_sec=5)
    _check(len(lines) == 4, f"겹침 1건 제거 후 4발화 (got {len(lines)})")
    _check(not any("버려져야" in ln for ln in lines), "겹침 구간 중복 세그먼트 제거됨")

    for ln in lines:
        parsed = parse_line(ln)
        _check(parsed is not None, f"parse_line 통과: {ln}")
    # 첫 줄 = 09:00:00, 강사(spk0)=00000000
    _check(lines[0].startswith("<09:00:00> 00000000:"), f"기준시각·hex 화자ID 정확: {lines[0]}")
    # 학생(spk1) → 00000001
    _check(any("00000001:" in ln for ln in lines), "학생 화자 hex=00000001")
    # 시간 단조 증가
    times = [parse_line(ln)[:3] for ln in lines]
    _check(times == sorted(times), "발화 시간 단조 증가")


def test_fmt():
    print("· 시각 포맷/오프셋")
    _check(start_seconds("09:00:00") == 32400, "09:00:00 → 32400초")
    _check(fmt_ts(32400 + 3725) == "10:02:05", "오프셋 누적 포맷")
    _check(fmt_ts(13 * 3600) == "13:00:00", "오후(13시) 그대로 — to_24h 이중보정 회피")


def main():
    print("STT 스모크 — 모델/ffmpeg 없이 배관 검증\n")
    test_parse_segments()
    test_plan_chunks()
    test_assemble_roundtrip()
    test_fmt()
    print("\n✅ 전부 통과 — transcript 포맷이 parse 파이프라인과 호환됩니다.")


if __name__ == "__main__":
    main()
