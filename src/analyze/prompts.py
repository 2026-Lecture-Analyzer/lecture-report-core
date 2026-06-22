"""분석 엔진(⑥) 프롬프트 — 유형별 LLM judge.

표준(라벨 없음): ⑤가 항목별 top-k 후보를 추리고, 여기 LLM 이 그 청크(+문맥)를 읽고
1~5점 채점 + 근거 인용(precision). 모든 프롬프트는 JSON 출력을 강제한다.

  judge_prompt   : 🟠 local / 🟢🟡 position — 항목 기준 + 근거 청크 → 채점
  global_prompt  : 🔴 global — 압축 전역뷰(개요·지표·샘플) → 구조 판정
  (🔵 metric 은 LLM 없이 metrics.score_metric_item 규칙 채점)

출력 JSON: {"score":1~5, "verdict":"...", "evidence":[{"chunk_id":int,"quote":str}],
            "comment":str, "needs_more":bool}
스키마는 docs/SCHEMA.md(analysis.jsonl)와 일치 유지.
"""
from __future__ import annotations

from src.analyze.checklist import CATEGORIES, SCORE_MAX, SCORE_MIN

_SCALE = (f"{SCORE_MAX}=명확히 우수 · 4=양호 · 3=보통 · 2=미흡 · "
          f"{SCORE_MIN}=거의/전혀 없음")

_JUDGE_SYS = (
    "너는 IT 강의의 질을 평가하는 교육 전문가다. 주어진 강의 발췌(청크)를 근거로 "
    "특정 평가 항목 하나를 채점한다. 원칙: "
    "(1) 발췌에 **실제로 나타난 근거만** 인용한다(추측·일반론 금지). "
    "(2) 해당 행동이 발췌에 없으면 점수를 낮추고 그 사실을 comment 에 적으며, "
    "evidence 는 빈 배열([])로 둔다(억지로 무관한 청크를 인용하지 않는다). "
    "(3) 근거가 부족해 판단이 어려우면 needs_more=true 로 표시한다. "
    "(4) **형식적 표현이 없어도 평이한 서술이면 인정한다** — 예: 개념 정의를 "
    "'A는 B를 의미합니다/이다/말합니다'로 풀어 설명해도 '정의'로, 같은 내용을 여러 번 "
    "말하면 '강조'로 인정한다. 명백한 관련 근거가 발췌에 있으면 '없음'으로 판정하지 않는다. "
    "여러 청크 중 일부만 관련 있어도 그 근거로 평가한다. "
    "(5) 반드시 아래 JSON 형식으로만 답한다."
)

_JSON_SPEC = (
    '{"score": 1~5 정수, "verdict": "우수/양호/보통/미흡/없음 중 하나", '
    '"evidence": [{"chunk_id": 정수, "quote": "발췌 원문 인용"}], '
    '"comment": "근거 기반 한두 문장", "needs_more": false}'
)

# 항목별 추가 채점 기준 — 공통 _JUDGE_SYS / 홀리스틱 프롬프트 위에 얹는 항목 특화 가이드.
# LLM 이 자주 틀리는 지점(단어만 보고 고득점, 무관 인용 등)을 항목별로 못박는다.
#
# ── 역할분담(프롬프트 수정) ────────────────────────────────────────────
#   각자 본인 카테고리 섹션의 키만 편집한다(서로 다른 키라 동시 작업해도 충돌 X).
#   C2 이지선 · C3 박채린 · C4 정찬희 · C5 김예슬
#   ※ 공통(_JUDGE_SYS·_SCALE·출력형식)과 다른 카테고리는 건드리지 말 것.
ITEM_GUIDES = {
    # ── C2 강의 구조 (담당: 이지선) ──────────────────────────────────────
    "C2_objective": (  # TODO(이지선): 고도화
        "강의 시작부에서 '오늘 배울 것/목표/진행 순서'를 안내하는지 본다. 인사·잡담이 아니라 "
        "학습 내용·목표를 짚어야 인정. 도입에 목표 언급이 전혀 없으면 1~2점."
    ),
    "C2_review": (
        "직전 차시 연결을 '지난 시간에/어제 ~했고', '아까 했던' 식으로 **짧게라도** 언급하면 "
        "인정한다. 별도 '복습' 섹션이 없어도 앞 내용을 오늘과 잇는 신호가 있으면 3점 이상, "
        "전혀 없으면 1~2점. 전사 곳곳의 '어제/지난 시간/앞에서' 연결을 놓치지 마라."
    ),
    "C2_structure": (
        "주제 나열과 '개념→예시→실습' 흐름을 구분하라. 개념 제시 후 예시/실습으로 "
        "이어지는 체계적 구조가 관찰되어야 한다. 순서가 뒤섞이거나 구조 없이 진행되면 "
        "점수를 낮춘다."
    ),
    "C2_emphasis": (  # TODO(이지선): 고도화
        "'중요하다/반드시/꼭/시험에 나온다' 등으로 핵심을 강조하거나 반복 전달하는지 본다. "
        "모든 내용을 평탄하게 전달하면 낮게, 강조 신호가 곳곳에 있으면 높게."
    ),
    "C2_summary": (  # TODO(이지선): 고도화
        "강의 끝 또는 매듭에서 핵심을 정리·요약하는지 본다. '오늘 배운 것은/정리하면' 식 신호. "
        "새 내용만 전달하고 정리 없이 끝나면 1~2점."
    ),
    # ── C3 개념 설명 명확성 (담당: 박채린) ───────────────────────────────
    "C3_definition": (
        "용어가 등장하는 것만으로 점수를 주지 마라. 그 용어의 '의미'를 풀어 설명한 "
        "문장이 있어야 한다. 의미 설명 없이 용어만 반복되면 2점 이하. "
        "쉬운 말로 풀거나 예·비유로 보완해 이해하기 쉽게 설명하면 높게 평가한다. "
        "이 항목은 강의의 핵심 주제 개념(예: '객체지향이란 현실 세계를 객체로 모델링하는 것')의 "
        "정의가 대상이다. 설명 중 등장하는 약어·전문어 풀이는 C3_term_explanation이 평가한다."
    ),
    "C3_term_explanation": (
        "전문 용어나 기술 용어를 언급만 했는지, 처음 등장 시 의미와 사용 맥락을 "
        "학습자가 이해할 수 있게 풀어 설명했는지 평가하라. 용어만 나열하면 낮게 평가한다. "
        "쉬운 말·비유·예시로 의미와 사용 맥락을 함께 설명하면 높게 평가한다. "
        "이 항목은 설명 중 등장하는 약어·전문어(예: 'API란 Application Programming Interface의 "
        "약자로 외부와 소통하는 창구입니다')가 대상이다. 강의 핵심 주제 개념의 정의는 C3_definition이 평가한다."
    ),
    "C3_analogy": (
        "비유·예시가 설명 중인 개념과 실제로 연결되는지 확인하라. '예를 들어' 뒤에 "
        "개념과 무관한 내용이 오거나 단순 사실 나열이면 인정하지 않는다. "
        "실생활 비유면 높게, '예를 들어 클래스를 만들면...'처럼 개념을 구체화하는 "
        "코드·사례 예시도 3~4점으로 인정한다. 코드 단순 시연·결과 제시는 인정하지 않는다. "
        "단, 코드 자체의 의도·흐름을 설명하는 것은 C3_code_explanation이 평가하므로 이 항목에서는 제외한다. "
        "근거 인용 시 비유 문장만이 아니라 어떤 개념을 설명하기 위한 비유인지 알 수 있도록 "
        "개념 설명 문장과 비유 문장을 함께 인용해야 한다."
    ),
    "C3_prerequisite": (
        "심화 내용에 진입하기 전에 선행 지식을 능동적으로 점검하거나 상기시키는지 본다. "
        "('앞에서 배운','이미 아시다시피' 등 확인 후 심화로 넘어가면 높게 평가한다.) "
        "선행 설명 없이 심화 용어가 갑자기 나오면 점수를 낮춘다. "
        "설명 중간에 이전 개념과 연결하는 것은 C3_concept_connection이 평가하므로 이 항목에서는 제외한다."
    ),
    "C3_concept_connection": (
        "설명 도중 현재 개념을 이 강의에서 이전에 학습한 개념·실습과 연결해 설명했는지 본다. "
        "단순히 여러 개념을 나열하거나 개념·직업군을 소개하는 문장은 연결성으로 보지 않는다. "
        "두 개념의 관계를 강사가 직접 설명해야 인정한다. "
        "심화 진입 전 선행 지식을 점검하는 것은 C3_prerequisite가 평가하므로 이 항목에서는 제외한다. "
        "근거 인용 시 현재 개념 설명 문장과 이전 개념과의 관계를 설명하는 문장을 함께 인용해야 한다."
    ),
    "C3_code_explanation": (
        "코드가 무엇을 하는지뿐 아니라 왜 그렇게 작성하는지, 어떤 의도와 흐름을 갖는지 "
        "설명했는지 평가한다. 코드 실행 결과만 보여주거나 줄 단위로 읽기만 하면 1~2점, "
        "의도(왜) 또는 흐름(어떻게) 중 하나만 설명하면 3점, 둘 다 설명하면 4~5점. "
        "근거 인용 시 코드 실행 결과를 읽는 문장이 아니라 의도나 흐름을 설명하는 문장을 직접 인용하라."
    ),
    # ── C4 진행 방식 (담당: 정찬희) ──────────────────────────────────────
    #   ※ C4_pace 는 raw 메트릭(분당 글자수, 규칙)이라 프롬프트 가이드 불필요.
    "C4_transition": (
        "주제 변경, 새로운 챕터 진입, 이론에서 실습으로 넘어가는 시점에 전환 멘트를 "
        "제공했는지 평가한다. 갑작스러운 주제 이동이면 낮게 평가한다."
    ),
    # ── C5 실습 및 적용 (담당: 김예슬) ───────────────────────────────────
    "C5_example": (  # TODO(김예슬): 고도화
        "예시가 학습 수준에 맞고 실무·실생활과 연관되는지 본다. '예를 들어' 뒤 예시가 개념과 "
        "직접 연결되면 인정. 구체적 수치 예시(예: 정확도 90%→8천원, MTBF 계산), 기업·서비스 "
        "사례(넷플릭스·KT·구글 PUE), 실생활 비교도 학습 수준에 맞는 실무 예시로 본다. "
        "이런 예시가 여러 개 분명하면 3점 이하로 깎지 말고 4점 이상. '동떨어졌다'는 판정은 "
        "예시가 설명 중인 개념과 실제로 무관할 때만. 예시 자체가 거의 없을 때만 1~2점."
    ),
    "C5_practice": (  # TODO(김예슬): 고도화
        "이론 설명 후 실습/적용으로 잇는지 본다. 강사가 쿼리를 직접 실행·시연하거나"
        "('인서트문을 실행해 보겠습니다'), 워밍업·연습 문제를 풀게 하거나, 배운 함수를 "
        "바로 적용해 보이면 — 학생이 직접 치지 않아도 '실습 연계 있음'으로 보고 3점 이상. "
        "이론↔실습 연결이 잦고 자연스러우면 4~5. 휴식 공지·UI 안내·순수 개념 설명만 있고 "
        "적용 시도가 전혀 없을 때만 1~2점."
    ),
}


def _render_chunks(chunks: list[dict], extra_label: str = "") -> str:
    lines = []
    for c in chunks:
        tag = f"{extra_label} " if extra_label else ""
        lines.append(f"[{tag}chunk {c['chunk_id']}] {c.get('clean_text', '')}")
    return "\n".join(lines)


def judge_prompt(item: dict, chunks: list[dict], context_chunks: list[dict] = None) -> list[dict]:
    """🟠 local / 🟢🟡 position 항목 채점. chunks=근거 후보, context_chunks=문맥확장(선택)."""
    body = _render_chunks(chunks)
    ctx = ""
    if context_chunks:
        ctx = ("\n[참고 문맥]\n"
               "앞뒤 의미 연결을 판단하기 위한 문맥이다. "
               "문맥 안에 실제 근거가 있으면 evidence 로 인용할 수 있다.\n"
               + _render_chunks(context_chunks, extra_label="ctx"))
    guide = ITEM_GUIDES.get(item["key"], "")
    user = (
        f"[평가 항목] {CATEGORIES[item['category']]} > {item['title']}\n"
        f"[판정 기준] {item['description']}\n"
        f"[항목별 추가 기준]\n{guide or '(없음)'}\n"
        f"[채점 척도] {_SCALE}\n\n"
        f"[강의 발췌]\n{body}{ctx}\n\n"
        f"위 항목을 채점하고 아래 JSON 으로만 답하라. evidence 의 chunk_id 는 발췌 번호.\n"
        f"{_JSON_SPEC}"
    )
    return [{"role": "system", "content": _JUDGE_SYS}, {"role": "user", "content": user}]


def global_prompt(item: dict, overview: dict, metrics: dict, sample_chunks: list[dict]) -> list[dict]:
    """🔴 global 항목 채점 — 압축 전역뷰(개요+지표+샘플)로 구조/일관성 판정."""
    kw = ", ".join((overview or {}).get("keywords", [])[:10]) or "(없음)"
    outline = "; ".join((overview or {}).get("outline", [])) or "(없음)"
    hr, ir = metrics.get("honorific_ratio"), metrics.get("incomplete_ratio")
    msig = (f"존댓말비율 {hr} (1.0=완전 존댓말 일관 · 0.5=반반 혼용), "
            f"미완결문장비율 {ir} (낮을수록 문장 완결), "
            f"분당 {metrics.get('pace_cpm')}자")
    guide = ("[지표 해석] 언어 일관성: 존댓말비율 0.9+면 대체로 일관(일부 혼용은 4점), "
             "0.7~0.9 다소 혼용(3점), 0.7 미만 비일관(1~2점). "
             "발화 완결성: 미완결비율 0.1 미만 우수(5점), 0.1~0.25 양호(4점), 0.25+ 미흡. "
             "※ 일부 인용에 보이는 혼용 1~2건만으로 과도하게 감점하지 말 것 — 비율을 우선한다.")
    sample = _render_chunks(sample_chunks)
    user = (
        f"[평가 항목] {CATEGORIES[item['category']]} > {item['title']}\n"
        f"[판정 기준] {item['description']}\n"
        f"[채점 척도] {_SCALE}\n\n"
        f"[강의 개요] 키워드: {kw} / 주제: {outline}\n"
        f"[전역 지표] {msig}\n"
        f"{guide}\n"
        f"[본문 샘플(흐름·어투 파악용)]\n{sample}\n\n"
        f"위 항목은 강의 전체의 구조/일관성을 보는 항목이다. 지표를 우선 근거로, 샘플은 보조로 "
        f"종합 채점하고 아래 JSON 으로만 답하라.\n{_JSON_SPEC}"
    )
    return [{"role": "system", "content": _JUDGE_SYS}, {"role": "user", "content": user}]


# ── 태그 0개 교차검증 ──────────────────────────────────────────────────
# 태깅(키워드+임베딩)이 후보를 0개 잡았을 때, 곧장 '부재(1점)'로 단정하면
# false negative 위험이 있다(태깅이 놓쳤을 뿐 실제로는 있을 수 있음).
# 균등 샘플 몇 개를 LLM 에 보여주고 "정말 없는지" 한 번 더 확인한다.
_CROSS_SYS = (
    "너는 IT 강의 평가자다. 특정 평가 항목에 해당하는 내용이 아래 발췌에 "
    "조금이라도 나타나는지만 판단한다. 키워드 검색이 놓쳤을 가능성을 고려해 "
    "표현이 달라도 의미가 맞으면 '있음'으로 본다. 반드시 JSON 으로만 답한다."
)

_CROSS_JSON = (
    '{"found": true/false, "score": 1~5 정수, '
    '"verdict": "우수/양호/보통/미흡/없음 중 하나", '
    '"evidence": [{"chunk_id": 정수, "quote": "발췌 원문 인용"}], '
    '"comment": "한두 문장", "needs_more": false}'
)


def cross_check_prompt(item: dict, sample_chunks: list[dict]) -> list[dict]:
    """태그 0개 항목의 교차검증. 샘플에서 항목 근거가 실제로 있는지 재확인."""
    guide = ITEM_GUIDES.get(item["key"], "")
    body = _render_chunks(sample_chunks)
    user = (
        f"[평가 항목] {CATEGORIES[item['category']]} > {item['title']}\n"
        f"[판정 기준] {item['description']}\n"
        f"[항목별 추가 기준]\n{guide or '(없음)'}\n\n"
        f"[강의 샘플]\n{body}\n\n"
        f"이 항목에 해당하는 내용이 위 샘플에 나타나는지 판단하라. "
        f"있으면 found=true 와 함께 채점하고, 정말 없으면 found=false 로 답하라.\n"
        f"{_CROSS_JSON}"
    )
    return [{"role": "system", "content": _CROSS_SYS}, {"role": "user", "content": user}]
