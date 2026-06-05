"""모델 출력에서 JSON 을 견고하게 추출.

LLM 이 코드펜스(```json)나 앞뒤 잡설을 붙여도 첫 번째 균형잡힌 {...} 또는
[...] 블록을 찾아 파싱한다. 실패 시 None.
"""
from __future__ import annotations

import json


def extract_json(text: str):
    if not text:
        return None
    # 코드펜스 제거
    t = text.strip()
    for fence in ("```json", "```JSON", "```"):
        if fence in t:
            t = t.split(fence, 1)[1]
            if "```" in t:
                t = t.rsplit("```", 1)[0]
            break
    # 균형 스캔으로 첫 JSON 객체/배열 추출
    for opener, closer in (("{", "}"), ("[", "]")):
        start = t.find(opener)
        if start == -1:
            continue
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == opener:
                    depth += 1
                elif c == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(t[start:i + 1])
                        except json.JSONDecodeError:
                            break
    try:
        return json.loads(t)
    except Exception:
        return None
