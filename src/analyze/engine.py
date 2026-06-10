"""분석 엔진(⑥) — chunks.jsonl → analysis.jsonl. 4갈래 라우팅 + 체크포인트/재개.

라우터: 항목 eval_type 으로 입력 분기(§⑥). 강의(=date_session) 단위로 18항목 평가.
  🔵 metric    : metrics 선계산 → 규칙 채점(LLM 없음)
  🟢🟡 position : 도입/종료 태깅 청크 → LLM judge (0개=부정 증거)
  🟠 local      : 태깅 top-k 청크 → LLM judge (+needs_more 시 문맥확장) (0개=부정 증거)
  🔴 global     : 개요+지표+샘플 압축뷰 → LLM judge

입력: chunks.jsonl(eval_tags) [+merged.jsonl(지표·문맥) +overview.json(전역)]
출력: analysis.jsonl — 항목 1건=1행. 이미 평가된 (lecture_id,item_key) 는 건너뜀(재개).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src import config
from src.analyze.checklist import CHECKLIST
from src.analyze.metrics import compute_metrics, score_global_metric_item, score_metric_item
from src.analyze.prompts import cross_check_prompt, global_prompt, judge_prompt
from src.refine.jsonout import extract_json

# 항목별 문맥확장 정책 — needs_more 시 앞/뒤로 가져올 인접 청크 수.
# 오류 대응(C4_error)은 해결책이 뒤에 오므로 after 를 넓게, 질문 응답(C5_answer)은
# 질문이 앞·답이 뒤이므로 양쪽을, 정의(C3_definition)는 좁게 본다.
# 미정의 항목은 _DEFAULT_CONTEXT 사용.
CONTEXT_POLICY = {
    "C4_error":       {"before": 1, "after": 3},
    "C5_answer":      {"before": 2, "after": 2},
    "C3_definition":  {"before": 1, "after": 1},
}
_DEFAULT_CONTEXT = {"before": 1, "after": 1}


def load_jsonl(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def group_by_lecture(records: list[dict]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        g[f"{r['date']}_{r['session']}"].append(r)
    return g


def _done_keys(out_path: Path) -> set:
    p = Path(out_path)
    if not p.exists():
        return set()
    done = set()
    for r in load_jsonl(p):
        done.add((r["lecture_id"], r["item_key"]))
    return done


def _tagged(item_key: str, chunks: list[dict], k: int) -> list[dict]:
    """item_key 로 태깅된 청크를 태그 score 내림차순 top-k."""
    scored = []
    for c in chunks:
        for t in c.get("eval_tags", []):
            if t["item_key"] == item_key:
                scored.append((t.get("score", t.get("sim", 0)), c))
                break
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


def _neighbors(target: list[dict], all_chunks: list[dict],
               before: int = 1, after: int = 1) -> list[dict]:
    """target 청크들의 chunk_id 인접 청크(문맥확장용, target 제외).

    before/after 로 앞뒤 폭을 비대칭 지정(CONTEXT_POLICY 반영).
    """
    by_id = {c["chunk_id"]: c for c in all_chunks}
    tids = {c["chunk_id"] for c in target}
    out, seen = [], set()
    for c in target:
        cid = c["chunk_id"]
        for nid in range(cid - before, cid + after + 1):
            if nid == cid:
                continue
            if nid in by_id and nid not in tids and nid not in seen:
                seen.add(nid)
                out.append(by_id[nid])
    return out


def _base_rec(item: dict, lid: str, meta: dict) -> dict:
    return {
        "lecture_id": lid, "file": meta["file"], "date": meta["date"],
        "session": meta["session"], "item_key": item["key"],
        "category": item["category"], "eval_type": item["eval_type"],
    }


def _to_int_score(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _aggregate(datas: list[dict]) -> dict:
    """self-consistency 다수결 — score 중앙값, 대표는 중앙값에 가깝고 근거 많은 샘플.

    raw score 들과 일치도(agreement)를 scoring_trace 로 남겨 점수 안정성을 검증 가능하게 한다.
    """
    valid = [(s, d) for d in datas if (s := _to_int_score(d.get("score"))) is not None]
    if not valid:
        out = dict(datas[0]) if datas else {}
        out["scoring_trace"] = {"raw_scores": [], "final_score": None, "agreement": 0.0}
        return out
    scores = sorted(s for s, _ in valid)
    n = len(scores)
    med = scores[n // 2] if n % 2 else round((scores[n // 2 - 1] + scores[n // 2]) / 2)
    best = min(valid, key=lambda sd: (abs(sd[0] - med), -len(sd[1].get("evidence") or [])))[1]
    out = dict(best)
    out["score"] = med
    out["needs_more"] = sum(1 for d in datas if d.get("needs_more")) * 2 >= len(datas)
    # agreement = 최종 점수(중앙값)와 동일한 raw score 비율
    raw = [s for s, _ in valid]
    agreement = round(sum(1 for s in raw if s == med) / len(raw), 2)
    out["scoring_trace"] = {"raw_scores": raw, "final_score": med, "agreement": agreement}
    return out


def _single_trace(data: dict) -> dict:
    """samples=1 일 때의 trace(단일 샘플)."""
    s = _to_int_score(data.get("score"))
    return {"raw_scores": [s] if s is not None else [],
            "final_score": s, "agreement": 1.0 if s is not None else 0.0}


def _as_dict(x) -> dict:
    """extract_json 이 배열을 돌려줄 때(모델이 [{...}] 로 답) 첫 dict 로 정규화.

    _aggregate/_single_trace 가 원소를 dict 로 가정하므로 list/None 은 여기서 흡수한다.
    """
    if isinstance(x, list):
        x = next((e for e in x if isinstance(e, dict)), None)
    return x if isinstance(x, dict) else {}


def _judge(messages, generate_fn, samples: int) -> dict:
    """채점 LLM 호출. samples>1 이면 반복 후 다수결 집계."""
    datas = [_as_dict(extract_json(generate_fn(messages))) for _ in range(max(1, samples))]
    if samples > 1:
        return _aggregate(datas)
    out = dict(datas[0])
    out["scoring_trace"] = _single_trace(datas[0])
    return out


def _from_llm(data: dict) -> dict:
    if isinstance(data, list):
        data = data[0] if data else {}
    score = data.get("score")
    try:
        score = int(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    verdict = (data.get("verdict") or "").strip()
    evidence = data.get("evidence") or []
    if verdict == "없음":          # 부재 판정엔 무관 인용 제거(안전장치)
        evidence = []
    return {
        "score": score, "verdict": verdict, "evidence": evidence, "metric": None,
        "comment": (data.get("comment") or "").strip(),
        "scoring_trace": data.get("scoring_trace"),
    }


def _validate_evidence(rec: dict) -> dict:
    """근거 없는 고득점 방지 — score>=4 인데 evidence 가 비면 신뢰할 수 없으므로 강등.

    LLM 이 근거를 인용하지 못하면서 높은 점수를 주는 경우(환각·일반론)를 막는다.
    metric 항목은 evidence 대신 수치(metric)로 평가하므로 이 검증을 적용하지 않는다.
    """
    if rec.get("metric") is not None:          # 지표 채점은 제외
        return rec
    score = rec.get("score")
    if score is not None and score >= 4 and not rec.get("evidence"):
        rec["score"] = 2
        rec["verdict"] = "근거 부족"
        rec["comment"] = (rec.get("comment", "") +
                          " [자동조정: 고득점이나 인용 근거가 없어 강등됨]").strip()
    return rec


def _negative(item: dict, cross_checked: bool = False) -> dict:
    """태깅 0개 = 항목 부재(부정 증거). cross_checked=교차검증을 거쳤는지."""
    return {"score": 1, "verdict": "없음", "evidence": [], "metric": None,
            "comment": "강의에서 해당 항목 관련 발화가 검색되지 않음(부정 증거).",
            "scoring_trace": {"raw_scores": [1], "final_score": 1, "agreement": 1.0},
            "_routing": {"n_candidates": 0, "expanded": 0,
                         "candidate_chunk_ids": [], "context_chunk_ids": [],
                         "negative_evidence": True, "cross_checked": cross_checked}}


def _global_sample(lec_chunks: list[dict], k: int, region: str = "all") -> list[dict]:
    """강의 청크에서 샘플 추출(전역 뷰·교차검증 공용).

    region:
      "all"   균등 간격 k개 (local·global)
      "head"  앞부분에서 k개 (intro 항목 — 도입부)
      "tail"  뒷부분에서 k개 (outro 항목 — 종료부)
    """
    ordered = sorted(lec_chunks, key=lambda c: c["chunk_id"])
    if len(ordered) <= k:
        return ordered
    if region == "head":
        return ordered[:k]
    if region == "tail":
        return ordered[-k:]
    step = len(ordered) / k
    return [ordered[int(i * step)] for i in range(k)]


def _cross_check_negative(item: dict, lec_chunks: list[dict],
                          generate_fn, samples: int) -> dict:
    """태깅 0개일 때 '정말 부재인지' 재확인(false negative 방지).

    위치형 항목은 해당 구간만 본다: intro→앞부분, outro→뒷부분, local→전체 균등.
    (마무리 요약을 중간 샘플에서 찾다 놓치는 문제 방지)
    LLM 이 found=true 로 근거를 찾으면 그 판정을 채택하고, 아니면 부재 확정.
    """
    region = {"intro": "head", "outro": "tail"}.get(item["eval_type"], "all")
    sample = _global_sample(lec_chunks, config.ANALYZE_GLOBAL_SAMPLE, region=region)
    data = _judge(cross_check_prompt(item, sample), generate_fn, samples)
    return data


def _eval_retrieval(item: dict, lec_chunks: list[dict], generate_fn, samples: int) -> dict:
    """🟠 local · 🟢🟡 position — 태깅 청크 → LLM judge (+문맥확장·교차검증·self-consistency)."""
    cands = _tagged(item["key"], lec_chunks, config.ANALYZE_EVIDENCE_K)

    # 태그 0개 → 부재 단정 전에 교차검증
    if not cands:
        cross = _cross_check_negative(item, lec_chunks, generate_fn, samples)
        if cross.get("found"):
            rec = _from_llm(cross)
            rec = _validate_evidence(rec)
            rec["_routing"] = {
                "n_candidates": 0, "expanded": 0, "samples": samples,
                "candidate_chunk_ids": [], "context_chunk_ids": [],
                "negative_evidence": False, "cross_checked": True,
            }
            return rec
        return _negative(item, cross_checked=True)

    cand_ids = [c["chunk_id"] for c in cands]
    pol = CONTEXT_POLICY.get(item["key"], _DEFAULT_CONTEXT)

    expanded = 0
    context: list[dict] = []
    data = _judge(judge_prompt(item, cands), generate_fn, samples)
    # local 만 문맥확장(position 은 위치 고정이라 생략). 정책의 before/after 를 회차만큼 확대.
    while (item["eval_type"] == "local" and data.get("needs_more")
           and expanded < config.ANALYZE_MAX_EXPAND):
        expanded += 1
        context = _neighbors(cands, lec_chunks,
                             before=pol["before"] * expanded,
                             after=pol["after"] * expanded)
        data = _judge(judge_prompt(item, cands, context_chunks=context), generate_fn, samples)

    rec = _from_llm(data)
    rec = _validate_evidence(rec)
    rec["_routing"] = {
        "n_candidates": len(cands), "expanded": expanded, "samples": samples,
        "candidate_chunk_ids": cand_ids,
        "context_chunk_ids": [c["chunk_id"] for c in context],
        "negative_evidence": False, "cross_checked": False,
    }
    return rec


def _eval_global(item: dict, lec_chunks: list[dict], overview: dict,
                 metrics: dict, generate_fn, samples: int) -> dict:
    """🔴 global — 개요+지표+균등 샘플 압축뷰로 채점.

    지표로 직접 채점 가능한 항목(C1_consistency·C1_completeness)은 규칙 점수를
    구해 LLM 점수와 혼합(평균)해 안정화한다. 지표가 없으면 LLM 단독.
    """
    sample = _global_sample(lec_chunks, config.ANALYZE_GLOBAL_SAMPLE)
    data = _judge(global_prompt(item, overview, metrics, sample), generate_fn, samples)
    rec = _from_llm(data)
    # NOTE: global 항목은 구조·일관성을 지표(존댓말비율 등) 기준으로 보므로
    # evidence(인용)가 비어도 정상이다. 따라서 _validate_evidence 를 적용하지 않는다.
    # (근거 없는 고득점 강등은 evidence 가 의미를 갖는 local/position 에만 적용)

    rule = score_global_metric_item(item["key"], metrics)
    mixed = False
    if rule is not None and rec.get("score") is not None:
        # LLM·규칙 평균(반올림)으로 혼합 — 규칙을 닻으로 삼아 전역 점수 안정화
        llm_score = rec["score"]
        rec["score"] = round((llm_score + rule["score"]) / 2)
        rec["metric"] = rule["value"]
        rec["comment"] = f"{rec.get('comment','')} | 지표: {rule['comment']}".strip(" |")
        mixed = True
    elif rule is not None:                  # LLM 점수 파싱 실패 → 규칙 단독
        rec["score"] = rule["score"]
        rec["metric"] = rule["value"]
        rec["comment"] = rule["comment"]
        mixed = True

    # 혼합으로 최종 점수가 바뀌었으면 scoring_trace 도 갱신(검증 일관성)
    if mixed:
        prev = rec.get("scoring_trace") or {}
        rec["scoring_trace"] = {
            "raw_scores": prev.get("raw_scores", []),
            "rule_score": rule["score"],
            "final_score": rec["score"],
            "agreement": prev.get("agreement"),
        }

    rec["_routing"] = {
        "n_candidates": len(sample), "expanded": 0, "samples": samples,
        "candidate_chunk_ids": [c["chunk_id"] for c in sample],
        "context_chunk_ids": [], "negative_evidence": False,
        "cross_checked": False, "rule_mixed": mixed,
    }
    return rec


def _eval_metric(item: dict, metrics: dict) -> dict:
    # merged.jsonl 부재 등으로 지표가 없으면 pace·filler 계산 불가 → N/A(평가 보류)
    if not metrics:
        return {"score": None, "verdict": "N/A", "evidence": [], "metric": None,
                "comment": "지표 계산 불가(merged.jsonl 없음) — 평가 보류.",
                "scoring_trace": {"raw_scores": [], "final_score": None, "agreement": None},
                "_routing": {"n_candidates": 0, "expanded": 0,
                             "candidate_chunk_ids": [], "context_chunk_ids": [],
                             "negative_evidence": False, "cross_checked": False}}
    m = score_metric_item(item["key"], metrics)
    return {"score": m["score"], "verdict": "", "evidence": [],
            "metric": m["value"], "comment": m["comment"],
            "scoring_trace": {"raw_scores": [m["score"]], "final_score": m["score"],
                              "agreement": 1.0},
            "_routing": {"n_candidates": 0, "expanded": 0,
                         "candidate_chunk_ids": [], "context_chunk_ids": [],
                         "negative_evidence": False, "cross_checked": False}}


def run_analysis(chunks_path: Path, generate_fn, out_path: Path,
                 merged_path: Path = None, overview_path: Path = None,
                 samples: int = None, log=print) -> dict:
    samples = config.ANALYZE_SELF_CONSISTENCY if samples is None else samples
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lectures = group_by_lecture(load_jsonl(chunks_path))

    merged_by_lec: dict[str, list[dict]] = {}
    if merged_path and Path(merged_path).exists():
        merged_by_lec = group_by_lecture(load_jsonl(merged_path))
    overviews: dict = {}
    if overview_path and Path(overview_path).exists():
        overviews = json.loads(Path(overview_path).read_text(encoding="utf-8"))

    done = _done_keys(out_path)
    if done:
        log(f"[resume] 이미 평가된 (강의,항목) {len(done)}쌍 건너뜀")

    n_new = 0
    with out_path.open("a", encoding="utf-8") as w:
        for lid, lec_chunks in lectures.items():
            meta = lec_chunks[0]
            clean_text = " ".join(c.get("clean_text", "") for c in lec_chunks)
            metrics = compute_metrics(merged_by_lec.get(lid, []), clean_text)
            for item in CHECKLIST:
                if (lid, item["key"]) in done:
                    continue
                et = item["eval_type"]
                if et == "metric":
                    body = _eval_metric(item, metrics)
                elif et == "global":
                    body = _eval_global(item, lec_chunks, overviews.get(lid), metrics,
                                        generate_fn, samples)
                else:  # local / intro / outro
                    body = _eval_retrieval(item, lec_chunks, generate_fn, samples)
                routing = body.pop("_routing")
                rec = {**_base_rec(item, lid, meta), **body, "routing": routing}
                w.write(json.dumps(rec, ensure_ascii=False) + "\n")
                w.flush()
                n_new += 1
            log(f"  {lid}: 18항목 평가 완료")

    return {"lectures": len(lectures), "new_rows": n_new,
            "skipped": len(done), "output": str(out_path)}
