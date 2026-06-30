"""전사·화자분리 프롬프트 + 모델 출력 → 세그먼트 파서.

세그먼트 계약: {"t": <클립시작 기준 초>, "spk": <정수 화자번호>, "text": <발화>}.
- spk 는 청크 간 안정성을 위해 "주 화자(가장 많이 말하는 강사)=0, 그 외=1,2.." 규칙을 강제.
- t 는 청크-상대 초. 원본 절대시각 오프셋은 stitch 단계에서 더한다.
"""
from __future__ import annotations

import json

TRANSCRIBE_SYS = (
    "너는 한국어 IT 강의 녹음을 전사하는 STT 엔진이다. 오디오를 듣고 발화를 시간순으로 "
    "받아쓰되, 화자를 구분한다. 추측으로 내용을 지어내지 말고 들리는 대로만 적는다."
)

_TRANSCRIBE_USER = """이 오디오(한국어 강의)를 전사하라. 규칙:
1) 발화를 의미 단위(대략 한 문장)로 끊어 시간순 세그먼트로 나눈다.
2) 각 세그먼트에 클립 시작 기준 **시작 시각(초, 소수 1자리)** 을 단다.
3) 화자 구분: 가장 많이 말하는 사람(강사)은 항상 spk=0, 그 외 사람은 등장 순서로 spk=1,2,...
4) 군더더기·간투사는 그대로 적되(정제는 다음 단계), 들리지 않는 부분은 생략한다.
5) 출력은 아래 JSON 배열 하나만. 설명·코드펜스 금지.

[{"t": 0.0, "spk": 0, "text": "발화 내용"}, {"t": 3.5, "spk": 0, "text": "..."}]
"""


def transcribe_messages() -> list[dict]:
    """transcribe_fn 에 넘길 메시지(시스템+유저). 오디오는 model 어댑터가 별도 첨부한다."""
    return [
        {"role": "system", "content": TRANSCRIBE_SYS},
        {"role": "user", "content": _TRANSCRIBE_USER},
    ]


def _extract_array(text: str):
    """모델 출력에서 첫 번째 균형잡힌 JSON 배열 [...] 을 추출(코드펜스·잡설 허용).

    refine 의 extract_json 은 {} 를 [] 보다 먼저 잡아 배열을 못 가져오므로, STT 전용으로
    배열만 균형 스캔한다.
    """
    if not text:
        return None
    t = text.strip()
    for fence in ("```json", "```JSON", "```"):
        if fence in t:
            t = t.split(fence, 1)[1]
            if "```" in t:
                t = t.rsplit("```", 1)[0]
            break
    start = t.find("[")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            esc = (c == "\\" and not esc)
            if c == '"' and not esc:
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_segments(text: str) -> list[dict]:
    """모델 출력 → 정규화된 세그먼트 리스트. 깨진 항목은 건너뛴다.

    t<0·결측 spk·빈 text 는 방어적으로 보정/제외한다. 항상 t 기준 정렬해 반환.
    """
    data = _extract_array(text)
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for seg in data:
        if not isinstance(seg, dict):
            continue
        txt = str(seg.get("text", "")).strip()
        if not txt:
            continue
        try:
            t = float(seg.get("t", 0.0))
        except (TypeError, ValueError):
            t = 0.0
        try:
            spk = int(seg.get("spk", 0))
        except (TypeError, ValueError):
            spk = 0
        out.append({"t": max(0.0, t), "spk": max(0, spk), "text": txt})
    out.sort(key=lambda s: s["t"])
    return out
