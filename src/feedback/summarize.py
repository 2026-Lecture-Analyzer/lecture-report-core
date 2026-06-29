"""학생 자유의견 → LLM 주제·감성 요약.

쌓인 자유 텍스트를 주제별로 묶고 감성(긍/부정)·대표 인용·강사 액션을 뽑는다.
generate_fn 주입(키 없이 stub 검증 가능). 출력은 구조화 dict.
"""
from __future__ import annotations

from src.refine.jsonout import extract_json

_SYS = ("너는 강의 피드백 분석가다. 수강생 자유의견을 읽고 주제별로 묶어 감성과 함께 정리하고, "
        "강사가 바로 실행할 개선 액션을 제안한다. 의견에 없는 내용을 지어내지 않는다.")


def summarize_prompt(comments: list[str]) -> list[dict]:
    joined = "\n".join(f"- {c}" for c in comments[:200])
    user = f"""다음은 한 강의에 대한 수강생 자유의견 {len(comments)}개다:
{joined}

아래 JSON 하나만 출력(코드펜스 금지):
{{"overall_sentiment": "긍정|중립|부정",
  "summary": "전체 1~2문장 요약",
  "themes": [{{"title": "주제", "sentiment": "긍정|중립|부정", "count": 정수(언급수 추정), "quote": "대표 인용"}}],
  "actions": ["강사가 바로 할 개선 1", "개선 2"]}}"""
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


def summarize_comments(comments: list[str], generate_fn) -> dict:
    """자유의견 리스트 → {overall_sentiment, summary, themes[], actions[]}. 비면 빈 구조."""
    comments = [c.strip() for c in comments if c and c.strip()]
    if not comments:
        return {"overall_sentiment": "", "summary": "", "themes": [], "actions": []}
    data = extract_json(generate_fn(summarize_prompt(comments))) or {}
    themes = []
    for t in (data.get("themes") or []):
        if not isinstance(t, dict):
            continue
        themes.append({"title": str(t.get("title", "")).strip(),
                       "sentiment": str(t.get("sentiment", "")).strip(),
                       "count": t.get("count") if isinstance(t.get("count"), int) else None,
                       "quote": str(t.get("quote", "")).strip()})
    return {
        "overall_sentiment": str(data.get("overall_sentiment", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "themes": [t for t in themes if t["title"]],
        "actions": [str(a).strip() for a in (data.get("actions") or []) if str(a).strip()],
    }
