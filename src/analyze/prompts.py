"""분석 엔진(P2) 프롬프트 — 체크리스트 항목별 LLM 평가.

담당: P2 (분석 엔진)
개발할 것: 체크리스트 18항목을 LLM이 채점하도록 하는 프롬프트 설계.
           강의 청크들을 근거로 특정 항목을 1~5점으로 평가.
입력 → 출력: item(체크리스트 항목) + chunks(한 강의 청크들) → chat 메시지 리스트
참고: docs/SCHEMA.md(analysis.jsonl), src/analyze/checklist.py(18항목 정의)
"""
from __future__ import annotations

from src.analyze.checklist import CATEGORIES, SCORE_MAX, SCORE_MIN  # noqa: F401


def item_prompt(item: dict, chunks: list[dict]) -> list[dict]:
    """단일 체크리스트 항목 평가 프롬프트(chat 메시지 리스트)를 만든다.

    item   : checklist.CHECKLIST 의 한 항목 {key, category, title, description}
    chunks : 한 강의(파일·세션)의 chunk 레코드 리스트
    반환   : [{"role": "system", ...}, {"role": "user", ...}]
    """
    # TODO(P2): system 프롬프트 — "근거(인용)만 사용, 추측 금지" 가드 포함
    # TODO(P2): user 프롬프트 — 항목 기준 + 청크 본문(chunk_id 표기) 제시
    # TODO(P2): JSON 출력 강제 — {score, verdict, evidence:[{chunk_id,quote}], comment}
    # TODO(P2): (선택) 항목별 few-shot 예시로 채점 일관성 향상
    # 참고 구현: 파일 하단 주석
    raise NotImplementedError("P2: 구현 필요 — 아래 참고 구현 참조")


# ════════════════════════════════════════════════════════════════════════
# 참고 구현 (Claude 초안 — 지우고 직접 작성하세요)
# ════════════════════════════════════════════════════════════════════════
# _SYS = (
#     "너는 IT 강의의 질을 평가하는 교육 전문가다. 주어진 강의 전사(청크들)를 "
#     "근거로 특정 평가 항목을 1~5점으로 채점한다. 반드시 전사에 실제로 나타난 "
#     "근거(인용)만 사용하고, 없으면 점수를 낮추고 그 사실을 적는다. 추측 금지."
# )
#
# def item_prompt(item: dict, chunks: list[dict]) -> list[dict]:
#     body = "\n".join(
#         f"[chunk {c['chunk_id']}] ({c.get('topic','')}) {c['clean_text']}"
#         for c in chunks
#     )
#     cat = CATEGORIES[item["category"]]
#     user = (
#         f"[평가 항목] {cat} > {item['title']}\n"
#         f"[판정 기준] {item['description']}\n\n"
#         f"[강의 전사 청크]\n{body}\n\n"
#         f"위 항목을 {SCORE_MIN}~{SCORE_MAX}점으로 채점하고 아래 JSON 으로만 답하라.\n"
#         '{"score": 4, "verdict": "양호/보통/미흡 중 하나", '
#         '"evidence": [{"chunk_id": 12, "quote": "실제 인용"}], '
#         '"comment": "근거 기반 한두 문장 평가"}'
#     )
#     return [{"role": "system", "content": _SYS},
#             {"role": "user", "content": user}]
