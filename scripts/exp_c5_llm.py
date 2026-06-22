"""[실험] C5 상호작용 — 발화 단위 LLM 의도분류 vs 키워드. 캘리브레이션·검증용 표 출력.

키워드 cue는 substring 매핑이라 '알겠지만'(수사)·'같이 사용'(서술)을 오탐. 표준(dialogue act):
키워드로 후보 발화(recall) → LLM이 발화별 "check/engage/none" 의도 판정(precision). 규칙 없이 일반화.

kdt 5 gold(raw 글로벌) + eval 8(클라우드)에 대해 키워드 per10 / LLM per10 / gold 를 한 표로.
사용:  LLM_BACKEND=upstage python -m scripts.exp_c5_llm
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import config  # noqa: E402
from src.refine.jsonout import extract_json  # noqa: E402
from src.refine.model import make_solar_generate_fn  # noqa: E402

CHK, ENG = set(config.C5_CHECK_CUES), set(config.C5_ENGAGE_CUES)

_SYS = (
    "너는 강의 발화 하나하나의 '상호작용 의도'를 분류한다. 각 발화를 정확히 하나로:\n"
    "• check = 수강생의 이해를 직접 확인하는 질문(되셨어요?/이해되죠?/알겠어요?/맞죠?). "
    "단 '~보시면 알겠지만'·'아시다시피'(공유경험 언급)나 '자/네/그쵸'(추임새)는 none.\n"
    "• engage = 수강생에게 직접 행동(풀기/실행/작성/입력)을 요청(해보세요/같이 풀어볼까요). "
    "단 '같이 사용하자'(서술)·'제가 해볼게요'(강사 시연)는 none.\n"
    "• none = 위 둘 다 아님.\n"
    "입력 발화 수만큼 라벨을 JSON 배열로만. 예: [\"none\",\"check\",\"engage\"]"
)


def classify(utts: list[str], gen, batch: int = 40) -> list[str]:
    out = []
    for i in range(0, len(utts), batch):
        ch = utts[i:i + batch]
        body = "\n".join(f"{j+1}. {u[:110]}" for j, u in enumerate(ch))
        arr = extract_json(gen([{"role": "system", "content": _SYS},
                                {"role": "user", "content": f"발화 {len(ch)}개:\n{body}\nJSON 배열:"}]))
        labs = [str(x).lower() for x in arr] if isinstance(arr, list) else []
        labs = (labs + ["none"] * len(ch))[:len(ch)]
        out += labs
    return out


def lecture_c5(utts: list[str], elapsed_min: float, gen) -> dict:
    cand_idx = [i for i, u in enumerate(utts) if any(c in u for c in CHK | ENG)]
    cand = [utts[i] for i in cand_idx]
    labs = classify(cand, gen) if cand else []
    llm_chk = sum(1 for x in labs if "check" in x)
    llm_eng = sum(1 for x in labs if "engage" in x)
    kw_chk = sum(u.count(c) for u in utts for c in CHK)
    kw_eng = sum(u.count(c) for u in utts for c in ENG)
    f = 10 / max(elapsed_min, 1e-6)
    return {"kw_chk": kw_chk * f, "kw_eng": kw_eng * f,
            "llm_chk": llm_chk * f, "llm_eng": llm_eng * f, "n_cand": len(cand)}


def main() -> None:
    from scripts.exp_gold_compare import GOLDS
    gen = make_solar_generate_fn(temperature=0)

    # kdt 5 gold (raw 글로벌 필터)
    raw_all = [json.loads(l) for l in (ROOT / "outputs/processed/raw.jsonl").open(encoding="utf-8")]
    lectures = []
    for d in ["2026-02-02", "2026-02-06", "2026-02-23", "2026-02-25", "2026-02-26"]:
        us = [r for r in raw_all if r.get("date") == d and r.get("text")]
        utts = [r["text"] for r in us]
        elapsed = (max(r["sec_of_day"] for r in us) - min(r["sec_of_day"] for r in us)) / 60
        g = GOLDS[d]
        lectures.append((f"kdt {d[5:]}", utts, elapsed, g["C5_check"], g["C5_engage"]))

    # eval 8 (클라우드) — labels.jsonl
    elab = {}
    for l in (ROOT.parent / "eval/labels/labels.jsonl").open(encoding="utf-8"):
        r = json.loads(l); elab.setdefault(r["lecture_id"], {})[r["item_key"]] = r["score"]
    for rp in sorted((ROOT.parent / "eval/processed").glob("*/raw.jsonl")):
        lid = rp.parent.name
        us = [json.loads(l) for l in rp.open(encoding="utf-8") if l.strip()]
        utts = [r["text"] for r in us if r.get("text")]
        elapsed = (max(r["sec_of_day"] for r in us) - min(r["sec_of_day"] for r in us)) / 60
        g = elab.get(lid, {})
        lectures.append((f"ev {lid[-6:]}", utts, elapsed, g.get("C5_check"), g.get("C5_engage")))

    from src.analyze.metrics import _band
    # LLM 카운트용 밴드(키워드보다 훨씬 작은 스케일 — genuine만 세므로)
    CB, EB = (0.3, 2.0, 4.0), (0.05, 1.0, 2.0)
    print(f"{'강의':12} {'kwChk':>6} {'llmChk':>6} {'gChk':>4} {'kwS/llmS':>8}  | "
          f"{'kwEng':>6} {'llmEng':>6} {'gEng':>4} {'kwS/llmS':>8}")
    print("-" * 78)
    err = {"kw_c": [], "llm_c": [], "kw_e": [], "llm_e": []}
    for name, utts, el, gc, ge in lectures:
        r = lecture_c5(utts, el, gen)
        kwc, llmc = _band(r["kw_chk"], *config.C5_CHECK_PER10), _band(r["llm_chk"], *CB)
        kwe, llme = _band(r["kw_eng"], *config.C5_ENGAGE_PER10), _band(r["llm_eng"], *EB)
        if gc is not None:
            err["kw_c"].append(abs(kwc - gc)); err["llm_c"].append(abs(llmc - gc))
        if ge is not None:
            err["kw_e"].append(abs(kwe - ge)); err["llm_e"].append(abs(llme - ge))
        print(f"{name:12} {r['kw_chk']:>6.2f} {r['llm_chk']:>6.2f} {str(gc):>4} {kwc}/{llmc:>6}  | "
              f"{r['kw_eng']:>6.2f} {r['llm_eng']:>6.2f} {str(ge):>4} {kwe}/{llme:>6}")
    def mae(k): return sum(err[k]) / len(err[k]) if err[k] else 0
    print("-" * 78)
    print(f"C5_check  평균|오차| vs gold:  키워드 {mae('kw_c'):.2f}   LLM {mae('llm_c'):.2f}")
    print(f"C5_engage 평균|오차| vs gold:  키워드 {mae('kw_e'):.2f}   LLM {mae('llm_e'):.2f}")


if __name__ == "__main__":
    main()
