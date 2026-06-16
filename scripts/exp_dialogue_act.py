"""[실험] C5 상호작용을 의도분류(dialogue act)로 — 키워드 후보 → LLM 검증 vs 키워드-only.

키워드 cue 는 recall↑ precision↓('같이' 오탐 등). 표준 접근(DA classification): 후보를 LLM이
"이해확인(check)/참여유도(engage)/아님(none)"으로 판정해 precision 확보. 비용은 후보만 1배치 호출.
비교: (키워드-only 카운트) vs (LLM-검증 카운트) vs gold(C5_check/engage).

사용:  python -m scripts.exp_dialogue_act --merged outputs/processed/_gold_0226/merged.jsonl --gold-date 2026-02-26
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.analyze.metrics import _band  # noqa: E402
from src.refine.jsonout import extract_json  # noqa: E402
from src.refine.model import make_solar_generate_fn  # noqa: E402

_SYS = (
    "너는 IT 강의 발화의 '상호작용 의도'를 분류하는 전문가다. 각 발화를 셋 중 하나로:\n"
    "• check = 수강생의 이해를 확인하는 질문/표현(되셨어요? 이해 가죠? 맞죠? 알겠어요?). "
    "단 단순 추임새(자/네/그쵸)나 강사 혼잣말성은 제외.\n"
    "• engage = 수강생에게 직접 행동(풀기/실행/작성/입력)을 요청하는 참여유도. "
    "단 강사 혼자 시연('제가 해볼게요')이나 '같이 사용하자'(서술)는 제외.\n"
    "• none = 위 둘 다 아님(내용 서술·일반 진술).\n"
    "반드시 입력 발화 수만큼의 라벨을 JSON 배열로만 답한다. 예: [\"none\",\"engage\",\"check\"]"
)


def _classify(utts: list[str], gen, batch: int = 40) -> list[str]:
    out = []
    for i in range(0, len(utts), batch):
        chunk = utts[i:i + batch]
        body = "\n".join(f"{j+1}. {u[:120]}" for j, u in enumerate(chunk))
        r = gen([{"role": "system", "content": _SYS},
                 {"role": "user", "content": f"발화 {len(chunk)}개 분류:\n{body}\n"
                  f"JSON 배열({len(chunk)}개)로만:"}])
        arr = extract_json(r)
        labs = arr if isinstance(arr, list) else []
        labs = [str(x).lower() for x in labs][:len(chunk)]
        labs += ["none"] * (len(chunk) - len(labs))     # 부족분 보충
        out += labs
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", type=Path, required=True)
    ap.add_argument("--gold-date", default=None)
    ap.add_argument("--backend", default="upstage")
    args = ap.parse_args()

    blocks = [json.loads(l) for l in args.merged.open(encoding="utf-8") if l.strip()]
    if args.gold_date:                       # 글로벌 merged 면 해당 날짜만
        blocks = [b for b in blocks if b.get("date") == args.gold_date] or blocks
    elapsed = max((max(b["end_sec"] for b in blocks) - min(b["start_sec"] for b in blocks)) / 60, 1e-6)

    chk, eng = set(config.C5_CHECK_CUES), set(config.C5_ENGAGE_CUES)
    cand = [b["text"] for b in blocks if any(c in b["text"] for c in chk | eng)]
    # 키워드-only 카운트(현행 메트릭과 동일 방식)
    kw_chk = sum(b["text"].count(c) for b in blocks for c in chk)
    kw_eng = sum(b["text"].count(c) for b in blocks for c in eng)

    print(f"블록 {len(blocks)} · cue 포함 후보 {len(cand)} · 경과 {elapsed:.0f}분 · 백엔드 {args.backend}")
    gen = make_solar_generate_fn(backend=args.backend, temperature=0)
    labs = _classify(cand, gen)
    llm_chk = sum(1 for x in labs if "check" in x)
    llm_eng = sum(1 for x in labs if "engage" in x)

    def score(n):
        return n  # placeholder
    c10_kw, e10_kw = kw_chk / elapsed * 10, kw_eng / elapsed * 10
    c10_llm, e10_llm = llm_chk / elapsed * 10, llm_eng / elapsed * 10
    s_kw = (_band(c10_kw, *config.C5_CHECK_PER10), _band(e10_kw, *config.C5_ENGAGE_PER10))
    s_llm = (_band(c10_llm, *config.C5_CHECK_PER10), _band(e10_llm, *config.C5_ENGAGE_PER10))

    print("\n           키워드-only        LLM-검증")
    print(f"이해확인   {kw_chk:>3}회 ({c10_kw:.2f}/10)   {llm_chk:>3}회 ({c10_llm:.2f}/10)   "
          f"제거 {kw_chk-llm_chk}")
    print(f"참여유도   {kw_eng:>3}회 ({e10_kw:.2f}/10)   {llm_eng:>3}회 ({e10_llm:.2f}/10)   "
          f"제거 {kw_eng-llm_eng}")
    print(f"점수(chk/eng)  키워드 {s_kw}   LLM {s_llm}", end="")
    if args.gold_date:
        from scripts.exp_gold_compare import GOLDS
        g = GOLDS.get(args.gold_date, {})
        print(f"   gold ({g.get('C5_check')}/{g.get('C5_engage')})")
    else:
        print()


if __name__ == "__main__":
    main()
