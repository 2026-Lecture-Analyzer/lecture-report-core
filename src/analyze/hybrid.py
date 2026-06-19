"""⑥-하이브리드 분석 코어 — raw 메트릭 + holistic 라우팅(공용).

run_hybrid_eval(실험·gold 대조)과 run_analyze_local(정식 진입점)이 함께 쓰는
하이브리드 평가 코어. holistic 으로 18항목을 채점한 뒤, 결정적 4항목만 raw 메트릭
점수로 **덮어쓴다**. 출력은 analysis.jsonl 동일 스키마 → 같은 스코어러/리포트/대시보드.

라우팅(신 기준):
  • raw 메트릭(결정적, LLM 없음) : C1_repetition · C1_completeness · C1_consistency · C4_pace
  • holistic(전체원문 1패스 LLM)  : 나머지 14항목

NOTE: holistic 평가 함수(evaluate_lecture, _lectures)는 현재 scripts/exp_holistic_eval.py 에
있어 함수 안에서 지연 import 한다(src→scripts 의존을 모듈 로드시 강제하지 않기 위함).
추후 holistic 코어도 src/analyze 로 옮기면 이 지연 import 를 일반 import 로 정리할 수 있다.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from src import config
from src.analyze.metrics import (compute_metrics, score_global_metric_item,
                                 score_metric_item)

# raw 메트릭으로 덮어쓸 결정적 항목 (나머지는 holistic 유지)
# C1·pace = 정제본이 신호를 지우거나 무뎌지게 함(§8) → raw(merged.text) 기준 규칙 채점.
METRIC_ITEMS = {"C1_repetition", "C1_completeness", "C1_consistency", "C4_pace"}

# 근거(evidence) 분리: 점수는 holistic, 근거는 항목별 임베딩 태깅(⑤ eval_tags)에서 top-k.
# holistic LLM 의 근거 선택이 약하고(엉뚱·중복·비결정적) → 항목별 검색 근거로 교체해
# "정의에 직접 부합·항목 전용·결정적" 근거를 준다. 태깅 없는 global 항목은 holistic 근거 유지.
RETRIEVAL_EVIDENCE_K = 3


def _chunks_by(chunks_path, by_date: bool) -> dict[str, list[dict]]:
    p = Path(chunks_path) if chunks_path else None
    if not p or not p.exists():
        return {}
    g: dict[str, list[dict]] = defaultdict(list)
    for line in p.open(encoding="utf-8"):
        if not line.strip():
            continue
        c = json.loads(line)
        g[c.get("date") if by_date else c.get("lecture_id")].append(c)
    return g


def _snippet(text: str, cue: str, maxlen: int = 80) -> str:
    """청크에서 근거가 될 대표 한 문장(가능하면 cue 포함) — 형광펜용이라 clean_text 그대로의 부분."""
    sents = re.split(r"(?<=[.!?])\s+", text or "")
    pick = next((s for s in sents if cue and cue in s), None) or (sents[0] if sents else text)
    return (pick or "").strip()[:maxlen]


def attach_retrieval_evidence(row: dict, lec_chunks: list[dict],
                              top_k: int = RETRIEVAL_EVIDENCE_K) -> bool:
    """row(holistic 채점)의 evidence 를 항목별 태깅 top-k 청크로 교체. 태깅 없으면 유지."""
    key = row["item_key"]
    cand = []
    for c in lec_chunks:
        for t in (c.get("eval_tags") or []):
            # cue(키워드 확정) 있는 태그만 — 순수 임베딩(cue=None)은 오탐 많음(휴식공지·UI 안내 등).
            if t.get("item_key") == key and t.get("cue"):
                cand.append((t.get("score", t.get("sim", 0)), c, t.get("cue", "")))
                break
    if not cand:
        return False
    cand.sort(key=lambda x: -(x[0] or 0))
    row["evidence"] = [{"chunk_id": c["chunk_id"], "time": (c.get("start_time") or "")[:5],
                        "quote": _snippet(c.get("clean_text", ""), cue)}
                       for _, c, cue in cand[:top_k]]
    row.setdefault("routing", {})["evidence_source"] = "retrieval"
    return True


def _metric_row(item_key: str, metrics: dict) -> dict | None:
    """item_key 의 raw 메트릭 채점 → {score, comment, metric}. 불가하면 None."""
    m = score_metric_item(item_key, metrics)
    if m["score"] is None:                       # global 지표형(C1_consistency/completeness)
        m = score_global_metric_item(item_key, metrics)
    if not m or m.get("score") is None:
        return None
    return {"score": m["score"], "comment": m["comment"], "metric": m["value"]}


def _merged_by(merged_path: Path, by_date: bool) -> dict[str, list[dict]]:
    if not merged_path or not Path(merged_path).exists():
        return {}
    blocks = [json.loads(l) for l in Path(merged_path).open(encoding="utf-8") if l.strip()]
    g: dict[str, list[dict]] = defaultdict(list)
    for b in blocks:
        lid = b["date"] if by_date else f"{b['date']}_{b['session']}"
        g[lid].append(b)
    return g


def _raw_texts_by(raw_path: Path, by_date: bool) -> dict[str, list[str]]:
    """raw.jsonl(정제 전 발화) → {lid: [발화텍스트]}. 완결성 발화단위 측정용."""
    if not raw_path or not Path(raw_path).exists():
        return {}
    g: dict[str, list[str]] = defaultdict(list)
    for l in Path(raw_path).open(encoding="utf-8"):
        if not l.strip():
            continue
        u = json.loads(l)
        lid = u["date"] if by_date else f"{u['date']}_{u['session']}"
        g[lid].append(u.get("text", ""))
    return g


def run_hybrid_analysis(clean_path: Path, merged_path: Path, raw_path: Path,
                        generate_fn, out_path: Path, samples: int = 3,
                        by_date: bool = False, backend: str = None,
                        only_lecture: str = None, chunks_path: Path = None,
                        log=print) -> dict:
    """하이브리드 평가 실행 → out_path(analysis.jsonl 스키마)에 항목별 1행씩 기록.

    반환: {"rows", "n_rows", "n_overwritten", "lectures", "output"}.
    rows 는 gold 대조 등 후처리를 위해 그대로 돌려준다.
    """
    # holistic 코어는 scripts 에 있어 지연 import (run_analyze_local --legacy 경로는 영향 없음).
    from scripts.exp_holistic_eval import _lectures, evaluate_lecture

    clean_path, out_path = Path(clean_path), Path(out_path)
    lecs = _lectures(clean_path, by_date=by_date)
    if only_lecture:
        lecs = {k: v for k, v in lecs.items() if k == only_lecture}
        if not lecs:
            raise SystemExit(f"강의 {only_lecture} 없음(clean): {clean_path}")

    merged_g = _merged_by(merged_path, by_date)
    raw_g = _raw_texts_by(raw_path, by_date)
    chunks_g = _chunks_by(chunks_path or config.PROCESSED_DIR / "chunks.jsonl", by_date)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    n_over_total = 0
    n_retr_total = 0
    with out_path.open("w", encoding="utf-8") as w:
        for lid, secs in lecs.items():
            rows = evaluate_lecture(lid, secs, generate_fn, samples,
                                    backend=backend or config.MODEL_BACKEND)
            metrics = compute_metrics(merged_g.get(lid, []), raw_texts=raw_g.get(lid))
            lec_chunks = chunks_g.get(lid, [])
            n_over = 0
            for r in rows:
                if r["item_key"] in METRIC_ITEMS and metrics:
                    mr = _metric_row(r["item_key"], metrics)
                    if mr:
                        r.update(score=mr["score"], comment=mr["comment"],
                                 metric=mr["metric"], evidence=[], verdict="")
                        r["routing"] = {"method": "raw_metric", "negative_evidence": False}
                        r["scoring_trace"] = {"raw_scores": [mr["score"]],
                                              "final_score": mr["score"], "agreement": 1.0}
                        n_over += 1
                else:
                    # holistic 항목 routing.method 명시(스키마 일관성, docs/SCHEMA.md §routing).
                    if not isinstance(r.get("routing"), dict):
                        r["routing"] = {}
                    r["routing"].setdefault("method", "holistic_fullcontext")
                    # 점수는 holistic, 근거는 항목별 태깅 top-k 로 교체(태깅 있으면).
                    if attach_retrieval_evidence(r, lec_chunks):
                        n_retr_total += 1
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
            all_rows += rows
            n_over_total += n_over
            scored = [r["score"] for r in rows if isinstance(r["score"], int)]
            log(f"  {lid}: 18항목(메트릭 덮어쓰기 {n_over}) · 평균 "
                f"{round(sum(scored)/len(scored),2) if scored else 'NA'}")

    return {"rows": all_rows, "n_rows": len(all_rows), "n_overwritten": n_over_total,
            "n_retrieval_evidence": n_retr_total,
            "lectures": len(lecs), "output": str(out_path)}
