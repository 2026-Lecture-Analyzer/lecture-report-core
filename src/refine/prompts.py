"""Step 3~5 프롬프트 템플릿.

각 함수는 chat 메시지 리스트([{role, content}, ...])를 반환한다.
모델 호출부(model.generate_fn)가 tokenizer.apply_chat_template 로 포맷한다.
모든 프롬프트는 **JSON 출력**을 요구해 후처리를 결정적으로 만든다.

스키마(입출력 JSON)는 docs/SCHEMA.md 와 일치 유지할 것.

[개선] refine_prompt:
    - [CTX] / [MAIN] 태그 처리 지시 추가
      → [CTX] 블록은 맥락 파악만, 출력에는 절대 포함하지 않는다.
      → [MAIN] 블록만 정제해 clean_text 에 출력한다.
    - 경계 복원 지시 추가
      → [MAIN] 첫/끝 문장이 [CTX] 내용과 이어지는 경우 자연스럽게 완성한다.
      → 단, 내용 추가·왜곡 금지 가드 유지.
    - [강의 개요] 전역 맥락 주입(§설계철학 A · overview.py)
      → 메타 대신 스크립트에서 뽑은 키워드·주제를 도메인 맥락으로 제공.
      → 용어 선택·STT 오류 복원 참고용. 개요 내용을 본문에 추가하지 않는다(가드).
"""
from __future__ import annotations

import json

# ── Step 3: 용어집 후보 추출 ───────────────────────────────────────────
_GLOSSARY_SYS = (
    "너는 한국어 IT 강의 STT(음성인식) 전사본을 교정하는 도우미다. "
    "전사본에는 음성인식 오류로 잘못 적힌 기술 용어가 많다. "
    "주어진 텍스트에서 (1) 잘못 표기된 기술용어와 올바른 표준 표기 쌍, "
    "(2) 자주 등장하는 핵심 도메인 용어를 찾아라."
)


def glossary_prompt(text: str) -> list[dict]:
    user = (
        "다음 강의 전사본 일부에서 STT 오류 후보와 핵심 용어를 추출해 "
        "아래 JSON 형식으로만 답하라. 확실하지 않으면 포함하지 마라.\n"
        '{"corrections": [{"wrong": "잡바", "correct": "Java"}], '
        '"terms": ["인덱스", "트랜잭션"]}\n\n'
        f"---\n{text}\n---"
    )
    return [{"role": "system", "content": _GLOSSARY_SYS},
            {"role": "user", "content": user}]


# ── Step 4: 섹션 정제 ──────────────────────────────────────────────────
_REFINE_SYS = (
    "너는 한국어 IT 강의 전사본을 읽기 좋은 문어체로 정제하는 편집자다.\n"
    "\n"
    "입력 형식:\n"
    "  [CTX][화자] 발화  → 앞뒤 맥락 블록. 문장 경계 파악에만 사용. 출력에 포함하지 않는다.\n"
    "  [MAIN][화자] 발화 → 실제 정제 대상. 이 블록의 내용만 clean_text 에 출력한다.\n"
    "\n"
    "정제 원칙:\n"
    "  (1) 의미·내용·예시는 절대 바꾸거나 추가하지 않는다.\n"
    "  (2) 군더더기/구어 간투사(이제, 저희가, 그다음에, 막, 뭐, 자, 어, 음 등)를 제거한다.\n"
    "  (3) 끊긴 발화를 자연스러운 문장으로 잇는다.\n"
    "  (4) 용어집에 따라 STT 오류 용어를 표준 표기로 고친다.\n"
    "  (5) [학생] 발화는 질문/답변 맥락이 중요하면 간결히 유지한다.\n"
    "  (6) [MAIN] 첫 문장이 앞 [CTX]와 문장 중간에서 이어진다면, "
    "앞 내용을 추가하지 말고 [MAIN] 첫 문장을 자연스러운 완전한 문장으로 시작되도록 정리한다.\n"
    "  (7) [MAIN] 마지막 문장이 뒤 [CTX]로 이어진다면, "
    "뒤 내용을 추가하지 말고 [MAIN] 마지막 문장을 자연스럽게 마무리한다.\n"
    "  (8) [CTX] 내용은 clean_text 에 단 한 글자도 포함하지 않는다.\n"
    "  (9) [강의 개요]는 이 강의 전체의 주제·키워드 맥락이다. 용어 선택과 STT 오류 "
    "복원의 참고로만 쓰고, 개요 내용을 clean_text 에 새로 추가하지 않는다."
)


def refine_prompt(section_text: str, glossary: dict, prev_summary: str,
                  overview: dict | None = None) -> list[dict]:
    gloss_str = json.dumps(glossary, ensure_ascii=False)
    ctx = prev_summary.strip() or "(없음 — 강의 시작 부분)"
    ov_block = ""
    if overview:
        kws = ", ".join(overview.get("keywords") or []) or "(없음)"
        outline = overview.get("outline") or []
        outline_str = "; ".join(outline) if outline else "(없음)"
        ov_block = f"[강의 개요]\n키워드: {kws}\n주제: {outline_str}\n\n"
    user = (
        f"{ov_block}"
        f"[용어집(JSON)]\n{gloss_str}\n\n"
        f"[직전 맥락 요약]\n{ctx}\n\n"
        f"[정제할 섹션 원문]\n{section_text}\n\n"
        "위 섹션에서 [MAIN] 블록만 정제하고, 다음 섹션에 넘길 1~2문장 요약을 작성해 "
        "아래 JSON 형식으로만 답하라.\n"
        '{"clean_text": "정제된 문어체 본문 ([MAIN]만)", "summary": "다음 맥락용 한두 문장 요약"}'
    )
    return [{"role": "system", "content": _REFINE_SYS},
            {"role": "user", "content": user}]


# ── Step 5: 주제 단위 청킹 ─────────────────────────────────────────────
_CHUNK_SYS = (
    "너는 정제된 한국어 강의 본문을 주제(소단원) 단위로 분할하는 도우미다. "
    "내용을 바꾸지 말고, 흐름이 전환되는 지점에서만 나눠라."
)


def chunk_prompt(clean_text: str) -> list[dict]:
    user = (
        "다음 정제된 강의 본문을 주제 단위로 나누고 각 조각에 짧은 주제 라벨을 붙여 "
        "아래 JSON 형식으로만 답하라. 원문 문장은 그대로 사용한다.\n"
        '{"chunks": [{"topic": "자바 IO 패키지 개요", "text": "..."}]}\n\n'
        f"---\n{clean_text}\n---"
    )
    return [{"role": "system", "content": _CHUNK_SYS},
            {"role": "user", "content": user}]
