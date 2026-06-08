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
from src.analyze.metrics import compute_metrics, score_metric_item
from src.analyze.prompts import global_prompt, judge_prompt
from src.refine.jsonout import extract_json


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


def _neighbors(target: list[dict], all_chunks: list[dict], width: int = 1) -> list[dict]:
    """target 청크들의 chunk_id 인접 청크(문맥확장용, target 제외)."""
    by_id = {c["chunk_id"]: c for c in all_chunks}
    tids = {c["chunk_id"] for c in target}
    out, seen = [], set()
    for c in target:
        for d in range(-width, width + 1):
            nid = c["chunk_id"] + d
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
    """self-consistency 다수결 — score 중앙값, 대표는 중앙값에 가깝고 근거 많은 샘플."""
    valid = [(s, d) for d in datas if (s := _to_int_score(d.get("score"))) is not None]
    if not valid:
        return datas[0] if datas else {}
    scores = sorted(s for s, _ in valid)
    n = len(scores)
    med = scores[n // 2] if n % 2 else round((scores[n // 2 - 1] + scores[n // 2]) / 2)
    best = min(valid, key=lambda sd: (abs(sd[0] - med), -len(sd[1].get("evidence") or [])))[1]
    out = dict(best)
    out["score"] = med
    out["needs_more"] = sum(1 for d in datas if d.get("needs_more")) * 2 >= len(datas)
    return out


def _judge(messages, generate_fn, samples: int) -> dict:
    """채점 LLM 호출. samples>1 이면 반복 후 다수결 집계."""
    datas = [extract_json(generate_fn(messages)) or {} for _ in range(max(1, samples))]
    return _aggregate(datas) if samples > 1 else datas[0]


def _from_llm(data: dict) -> dict:
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
    }


def _negative(item: dict) -> dict:
    """태깅 0개 = 항목 부재(부정 증거)."""
    return {"score": 1, "verdict": "없음", "evidence": [], "metric": None,
            "comment": "강의에서 해당 항목 관련 발화가 검색되지 않음(부정 증거).",
            "_routing": {"n_candidates": 0, "expanded": 0,
                         "negative_evidence": True, "cross_checked": False}}


def _eval_retrieval(item: dict, lec_chunks: list[dict], generate_fn, samples: int) -> dict:
    """🟠 local · 🟢🟡 position — 태깅 청크 → LLM judge (+문맥확장·self-consistency)."""
    cands = _tagged(item["key"], lec_chunks, config.ANALYZE_EVIDENCE_K)
    if not cands:
        return _negative(item)

    expanded = 0
    data = _judge(judge_prompt(item, cands), generate_fn, samples)
    # local 만 문맥확장(position 은 위치 고정이라 생략)
    while (item["eval_type"] == "local" and data.get("needs_more")
           and expanded < config.ANALYZE_MAX_EXPAND):
        expanded += 1
        context = _neighbors(cands, lec_chunks, width=expanded)
        data = _judge(judge_prompt(item, cands, context_chunks=context), generate_fn, samples)

    rec = _from_llm(data)
    rec["_routing"] = {"n_candidates": len(cands), "expanded": expanded,
                       "samples": samples, "negative_evidence": False, "cross_checked": False}
    return rec


def _eval_global(item: dict, lec_chunks: list[dict], overview: dict,
                 metrics: dict, generate_fn, samples: int) -> dict:
    """🔴 global — 개요+지표+균등 샘플 압축뷰로 채점(self-consistency)."""
    k = config.ANALYZE_GLOBAL_SAMPLE
    ordered = sorted(lec_chunks, key=lambda c: c["chunk_id"])
    if len(ordered) <= k:
        sample = ordered
    else:
        step = len(ordered) / k
        sample = [ordered[int(i * step)] for i in range(k)]
    data = _judge(global_prompt(item, overview, metrics, sample), generate_fn, samples)
    rec = _from_llm(data)
    rec["_routing"] = {"n_candidates": len(sample), "expanded": 0,
                       "samples": samples, "negative_evidence": False, "cross_checked": False}
    return rec


def _eval_metric(item: dict, metrics: dict) -> dict:
    m = score_metric_item(item["key"], metrics)
    return {"score": m["score"], "verdict": "", "evidence": [],
            "metric": m["value"], "comment": m["comment"],
            "_routing": {"n_candidates": 0, "expanded": 0,
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
