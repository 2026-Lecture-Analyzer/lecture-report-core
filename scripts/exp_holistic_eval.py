"""[실험] 전체원문 holistic 평가 — clean.jsonl 한 강의 전체를 1프롬프트로 18항목 일괄 채점.

현재 RAG(항목→top-5 청크 retrieval)와 비교하기 위한 **대조군**. refine 산출(clean.jsonl)이
강의당 ~6~8k 토큰밖에 안 돼 전체가 한 컨텍스트에 들어가므로, 평가요소마다 원문 일부만 보던
한계를 없애고 "각 항목이 강의 전체를 본다"를 구현한다.

기존 파이프라인 무수정. 출력은 analysis.jsonl 과 **동일 스키마** → 같은 스코어러로 사과-대-사과 비교.

사용법:
    # 빌드만(프롬프트·토큰 확인, API 호출 없음)
    python -m scripts.exp_holistic_eval --dry-run
    # 실제 실행(Upstage/Google 백엔드는 .env LLM_BACKEND 따름) + RAG 와 점수 비교표
    python -m scripts.exp_holistic_eval --self-consistency 3 --compare
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.analyze.checklist import CATEGORIES, CHECKLIST, SCORE_MAX, SCORE_MIN  # noqa: E402
from src.analyze.prompts import ITEM_GUIDES  # noqa: E402
from src.refine.model import make_solar_generate_fn  # noqa: E402

_SCALE = (f"{SCORE_MAX}=명확히 우수 · 4=양호 · 3=보통 · 2=미흡 · "
          f"{SCORE_MIN}=거의/전혀 없음")

_SYS = (
    "너는 IT 강의의 질을 평가하는 교육 전문가다. 강의 전사(전체)를 처음부터 끝까지 읽고, "
    "주어진 18개 평가 항목을 **각각 강의 전체 근거에 비추어** 채점한다. 원칙: "
    "(1) 전사에 실제로 나타난 근거만 인용한다(추측·일반론 금지). "
    "(2) 빈도/일관성 항목은 강의 전반을 훑어 판단한다(일부 구간만 보지 않는다). "
    "(3) 해당 행동이 전혀 없으면 낮게 주고 evidence 는 빈 배열로 둔다. "
    "(4) 형식적 표현이 없어도 평이한 서술이면 인정한다. "
    "(5) 반드시 지정한 JSON 배열로만 답한다(설명 텍스트 금지)."
)

# Google(Gemini) 전용 채점 보정 — flash 는 박하게(편향 -1.1), pro 는 후하게(+1.2) 치우쳐
# 사람 채점과 안 맞음(gold 검증). 척도를 구체 앵커로 못박아 편향을 잡는다. Upstage 경로엔 미적용.
_GOOGLE_CALIB = (
    "\n[채점 보정 — 반드시 준수]\n"
    "점수를 깎지도 부풀리지도 말고 아래 앵커에 맞춰라:\n"
    "• 5 = 해당 행동이 명확하고 반복적으로 나타남\n"
    "• 4 = 분명히 나타나며 대체로 잘함(일부 미흡 허용) — 양호한 일반 강의의 기본값\n"
    "• 3 = 보통 수준으로 존재(평이하게라도 수행함)\n"
    "• 2 = 약하거나 드물게만 나타남\n"
    "• 1 = 거의/전혀 없음\n"
    "실제 강의의 대부분 항목은 3~4점에 분포한다. 평이한 서술로라도 근거가 있으면 3 이상으로 "
    "인정하고, 명백한 결함이 있을 때만 2 이하를 준다. 한두 군데 흠으로 과도하게 깎지 마라.\n"
)


def _calib(backend: str | None) -> str:
    return _GOOGLE_CALIB if backend in ("google", "gemini") else ""


def _lectures(clean_path: Path, by_date: bool = False) -> dict[str, list[dict]]:
    """clean.jsonl → {lecture_id: 섹션들}. by_date=True 면 오전+오후를 하루로 합침.

    holistic 은 전체를 한 번에 읽으므로 day 단위 채점이 자연스럽다(도입/요약처럼 하루
    한 번만 나오는 항목을 세션 평균으로 깎지 않음). lecture_id 는 date(예: 2026-02-02).
    """
    recs = [json.loads(l) for l in clean_path.open(encoding="utf-8") if l.strip()]
    g: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        lid = r["date"] if by_date else f"{r['date']}_{r['session']}"
        g[lid].append(r)
    # day 모드: 세션(오전→오후)·섹션 순으로 정렬해 시간순 전사
    order = {"오전": 0, "오후": 1}
    for lid in g:
        g[lid].sort(key=lambda r: (order.get(r.get("session"), 0), r.get("section_id", 0)))
    return g


def _transcript(sections: list[dict]) -> str:
    """타임스탬프 부착 전체 전사 — [HH:MM] 정제발화."""
    lines = []
    for s in sections:
        t = (s.get("start_time") or "")[:5]
        lines.append(f"[{t}] {s.get('clean_text', '')}")
    return "\n".join(lines)


def _rubric() -> str:
    """18항목 루브릭 블록 — 항목별 기준 + 추가 가이드."""
    out = []
    for it in CHECKLIST:
        guide = ITEM_GUIDES.get(it["key"], "")
        line = (f"- {it['key']} · [{CATEGORIES[it['category']]}] {it['title']} "
                f"(가중치 {it['weight']})\n    기준: {it['description']}")
        if guide:
            line += f"\n    추가: {guide}"
        out.append(line)
    return "\n".join(out)


def build_messages(sections: list[dict], backend: str | None = None) -> list[dict]:
    keys = ", ".join(it["key"] for it in CHECKLIST)
    user = (
        f"[채점 척도] {_SCALE}{_calib(backend)}\n\n"
        f"[평가 항목 18개]\n{_rubric()}\n\n"
        f"[강의 전사 — 전체]\n{_transcript(sections)}\n\n"
        f"위 18개 항목을 강의 전체 근거로 각각 채점하라. 반드시 18개 전부, "
        f"아래 JSON 배열로만 답한다(item_key 는 위 목록 그대로: {keys}).\n"
        "각 항목 evidence 는 그 항목 정의에 '직접' 부합하는 발화만 골라라 — 다른 항목과 같은 "
        "문장을 재사용하지 말고, 가장 강하게 부합하는 것부터 2~4개(있는 만큼). "
        "quote 는 60자 이내, comment 는 한 문장.\n"
        '[{"item_key":"C1_repetition","score":1~5 정수,'
        '"verdict":"우수/양호/보통/미흡/없음 중 하나",'
        '"evidence":[{"time":"HH:MM","quote":"≤60자 인용"}],'
        '"comment":"한 문장"}, ... 18개 전부]'
    )
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


def _collect_objects(text: str) -> list[dict]:
    """배열/잘린 응답에서 **완성된 top-level {…} 객체만** 모은다.

    extract_json 은 배열 첫 객체만 반환하고 truncate 에 약하다. 여기선 문자열/이스케이프를
    추적하며 균형 잡힌 {…} 를 하나씩 파싱 — 끝이 잘려도 직전까지의 완성 객체는 살린다.
    """
    objs: list[dict] = []
    depth = 0
    start = None
    in_str = esc = False
    for i, c in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        objs.append(json.loads(text[start:i + 1]))
                    except json.JSONDecodeError:
                        pass
                    start = None
    return objs


def _parse_items(raw: str) -> dict[str, dict]:
    """LLM 응답 → {item_key: obj}. 배열·코드펜스·truncate 모두 흡수(완성 객체만)."""
    out = {}
    for o in _collect_objects(raw):
        if o.get("item_key"):
            out[o["item_key"]] = o
    return out


def _median(xs: list[int]):
    xs = sorted(x for x in xs if isinstance(x, int))
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2)


def evaluate_lecture(lid: str, sections: list[dict], generate_fn, samples: int,
                     backend: str | None = None) -> list[dict]:
    """holistic 채점 → analysis.jsonl 호환 행 리스트(18개). self-consistency=항목별 중앙값.

    lid 는 그룹 키(세션 모드=date_session, day 모드=date). session 은 lid 에서 유도.
    """
    meta = sections[0]
    session = meta["session"] if "_" in lid else "전체"
    runs = [_parse_items(generate_fn(build_messages(sections, backend)))
            for _ in range(max(1, samples))]

    rows = []
    for it in CHECKLIST:
        k = it["key"]
        cand = [r[k] for r in runs if k in r]
        scores = [c.get("score") for c in cand if isinstance(c.get("score"), int)]
        med = _median(scores)
        # 대표 샘플 = 중앙값에 가장 가깝고 근거 많은 것
        rep = min(cand, key=lambda c: (abs((c.get("score") or 0) - (med or 0)),
                                       -len(c.get("evidence") or [])), default={})
        rows.append({
            "lecture_id": lid,
            "file": meta.get("file"), "date": meta["date"], "session": session,
            "item_key": k, "category": it["category"], "eval_type": it["eval_type"],
            "score": med, "verdict": rep.get("verdict", "" if med else "없음"),
            "evidence": rep.get("evidence") or [], "metric": None,
            "comment": rep.get("comment", "" if cand else "응답 없음(파싱 실패)"),
            "scoring_trace": {"raw_scores": scores, "final_score": med,
                              "agreement": round(scores.count(med) / len(scores), 2) if scores else 0.0},
            "routing": {"method": "holistic_fullcontext", "samples": samples,
                        "n_candidates": len(sections), "negative_evidence": med == 1 and not (rep.get("evidence")),
                        "missing": k not in runs[0] if runs else True},
        })
    return rows


def _compare(rag_path: Path, holistic_path: Path) -> None:
    from src.scoring.scoring import compute_scores
    rag = [json.loads(l) for l in rag_path.open(encoding="utf-8") if l.strip()] if rag_path.exists() else []
    hol = [json.loads(l) for l in holistic_path.open(encoding="utf-8") if l.strip()]
    rag_by = {(r["lecture_id"], r["item_key"]): r for r in rag}
    print("\n" + "=" * 78)
    print("항목별 점수 비교  (RAG = 현재 top-5 retrieval · HOL = 전체원문 holistic)")
    print("=" * 78)
    lids = sorted({r["lecture_id"] for r in hol})
    for lid in lids:
        print(f"\n▶ {lid}")
        print(f"  {'item':16} {'type':7} {'RAG':>4} {'HOL':>4}  Δ")
        for it in CHECKLIST:
            h = next((r for r in hol if r["lecture_id"] == lid and r["item_key"] == it["key"]), None)
            r = rag_by.get((lid, it["key"]))
            hs = h["score"] if h else None
            rs = r["score"] if r else None
            d = (hs - rs) if isinstance(hs, int) and isinstance(rs, int) else None
            mark = "" if d in (0, None) else ("  ▲" if d > 0 else "  ▼")
            print(f"  {it['key']:16} {it['eval_type']:7} {str(rs):>4} {str(hs):>4} {(f'{d:+d}' if d is not None else '·'):>4}{mark}")
    # 종합
    print("\n" + "-" * 78)
    sc_h = compute_scores(hol)["lectures"]
    sc_r = compute_scores(rag)["lectures"] if rag else {}
    print(f"  {'lecture':22} {'RAG 종합':>10} {'HOL 종합':>10}   (1주차 기준: 오전 42.2 / 오후 31.1)")
    for lid in lids:
        rt = sc_r.get(lid, {}).get("total_score")
        ht = sc_h.get(lid, {}).get("total_score")
        print(f"  {lid:22} {str(rt):>10} {str(ht):>10}")
    print("=" * 78)


def main() -> None:
    ap = argparse.ArgumentParser(description="[실험] 전체원문 holistic 평가 vs RAG")
    ap.add_argument("--clean", type=Path, default=config.PROCESSED_DIR / "clean.jsonl")
    ap.add_argument("--out", type=Path, default=config.PROCESSED_DIR / "holistic_analysis.jsonl")
    ap.add_argument("--lecture", default=None, help="한 강의만(date_session)")
    ap.add_argument("--backend", default=None, help="upstage|google|hf (기본 .env)")
    ap.add_argument("--self-consistency", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, default=8000, help="18항목 출력 여유(기본 1024는 부족)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--compare", action="store_true", help="실행 후 RAG(analysis.jsonl)와 점수 비교표")
    ap.add_argument("--by-date", action="store_true",
                    help="오전+오후를 하루로 합쳐 day 단위 채점(gold 가 하루 전체일 때 공정 비교)")
    args = ap.parse_args()

    if not args.clean.exists():
        sys.exit(f"clean 없음: {args.clean} — 먼저 정제(run_refine_local) 실행")
    lecs = _lectures(args.clean, by_date=args.by_date)
    if args.lecture:
        lecs = {k: v for k, v in lecs.items() if k == args.lecture}
        if not lecs:
            sys.exit(f"강의 {args.lecture} 없음")

    print("─" * 60)
    print(f"백엔드 : {args.backend or config.MODEL_BACKEND} · self-consistency {args.self_consistency}")
    for lid, secs in lecs.items():
        chars = sum(len(s.get("clean_text", "")) for s in secs)
        print(f"강의 {lid}: {len(secs)}섹션 · {chars:,}자 ≈ ~{chars // 2}토큰 입력")
    n_calls = len(lecs) * args.self_consistency
    print(f"LLM 호출: 강의 {len(lecs)}편 × SC {args.self_consistency} = {n_calls}건 (RAG 의 ~16배 적음)")
    print(f"산출   : {args.out}")
    print("─" * 60)

    if args.dry_run:
        first = next(iter(lecs.values()))
        msgs = build_messages(first)
        print("[dry-run] 시스템+유저 프롬프트 미리보기(앞 1200자):\n")
        print(msgs[1]["content"][:1200])
        print(f"\n... [생략] 유저 프롬프트 총 {len(msgs[1]['content']):,}자")
        return

    try:
        generate_fn = make_solar_generate_fn(backend=args.backend, max_tokens=args.max_tokens,
                                             temperature=config.ANALYZE_SC_TEMPERATURE
                                             if args.self_consistency > 1 else 0)
    except RuntimeError as e:
        sys.exit(f"[키 오류] {e}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    all_rows = []
    with args.out.open("w", encoding="utf-8") as w:
        for lid, secs in lecs.items():
            rows = evaluate_lecture(lid, secs, generate_fn, args.self_consistency,
                                    backend=args.backend or config.MODEL_BACKEND)
            for r in rows:
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
            all_rows += rows
            scored = [r["score"] for r in rows if isinstance(r["score"], int)]
            na = sum(1 for r in rows if r["score"] is None)
            print(f"  {lid}: 18항목 · 평균 {round(sum(scored)/len(scored),2) if scored else 'NA'} · N/A {na}")
    print(f"[holistic] {len(all_rows)}행 → {args.out}")

    if args.compare:
        _compare(config.PROCESSED_DIR / "analysis.jsonl", args.out)


if __name__ == "__main__":
    main()
