"""강의 개요 추출(Step 3, §2) — 키워드 + 주제 아웃라인.

메타데이터를 input으로 못 쓰므로(정답 전용), 강의 주제·키워드를 **스크립트에서 직접**
뽑아 정제(④)의 전역 맥락으로 쓴다.
  - 키워드: KoNLPy 명사빈도 (무료·길이무관) — 항상 가능.
  - 주제 아웃라인: generate_fn(LLM) map-reduce — 선택(없으면 키워드만).

요약 분리 원칙(§2): 여기 아웃라인은 '정제 전 거친 가이드'. 최종 요약은 정제 후 별도.
"""
from __future__ import annotations

from src import config
from src.preprocess import text as textmod
from src.refine.jsonout import extract_json
from src.refine.prompts import _CHUNK_SYS  # noqa: F401  (스타일 참고용)


def extract_keywords(texts: list[str], top_k: int = None) -> list[str]:
    """KoNLPy 명사빈도 상위 키워드(불용어 제거는 noun_counts 내부 처리)."""
    top_k = config.OVERVIEW_TOP_KEYWORDS if top_k is None else top_k
    counter = textmod.noun_counts(texts)
    return [w for w, _ in counter.most_common(top_k)]


def _outline_prompt(joined_summaries: str, keywords: list[str]) -> list[dict]:
    sys = ("너는 강의 전사를 보고 핵심 주제 개요를 만드는 도우미다. "
           "내용을 지어내지 말고 실제 등장한 주제만 간결히 정리한다.")
    user = (f"[핵심 키워드] {', '.join(keywords)}\n\n"
            f"[부분 요약들]\n{joined_summaries}\n\n"
            "이 강의의 주제 개요를 3~6개 항목으로 요약해 아래 JSON으로만 답하라.\n"
            '{"outline": ["주제1", "주제2"]}')
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def build_overview(texts: list[str], generate_fn=None,
                   chunk_chars: int = 4000) -> dict:
    """강의 1편 개요. texts = 그 강의의 (정제/병합) 텍스트 조각들.

    반환: {"keywords": [...], "outline": [...]}  (generate_fn 없으면 outline=[])
    """
    keywords = extract_keywords(texts)
    outline: list[str] = []
    if generate_fn is not None and texts:
        # map: 큰 덩어리별 한 줄 요약 → reduce: 개요
        joined, buf, size = [], [], 0
        for t in texts:
            if size + len(t) > chunk_chars and buf:
                joined.append(" ".join(buf)); buf, size = [], 0
            buf.append(t); size += len(t)
        if buf:
            joined.append(" ".join(buf))
        partials = []
        for piece in joined:
            out = generate_fn([
                {"role": "system", "content": "다음 강의 일부를 한 문장으로 요약하라."},
                {"role": "user", "content": piece[:chunk_chars]},
            ])
            partials.append(out.strip().split("\n")[0])
        data = extract_json(generate_fn(_outline_prompt("\n".join(partials), keywords))) or {}
        outline = data.get("outline", []) or []
    return {"keywords": keywords, "outline": outline}
