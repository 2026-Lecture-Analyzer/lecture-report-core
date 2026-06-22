"""평가항목 태깅(§9) — **항목당 top-k 검색**(표준 RAG: dense retrieve → ⑥ LLM judge).

표준 패턴(라벨 없을 때): 임베딩으로 항목별 관련 청크 top-k 만 추리고(recall),
정밀 판정은 ⑥ 분석의 LLM 이 그 청크+문맥을 읽고 한다(precision). 그래서 여기는
**완벽할 필요 없는 후보 생성기** — "임계값 넘는 거 전부"(과태깅)가 아니라 항목당 top-k.

신호(문헌: RubricRAG=dense 검색, DAT=dense+키워드 가중):
  (1) **dense 임베딩 유사도**(chunk vs 항목 description) — 주 신호(랭킹 기준).
  (2) 시드 키워드 매칭 — 보조. 동점 시 가산점(TAG_KEYWORD_BONUS)만, 단독 태깅 X.

검색 규칙(항목마다):
    후보 = 위치게이트 & ( sim ≥ TAG_RETRIEVE_FLOOR  OR  cue & sim ≥ TAG_FLOOR_KW )
    태깅 = 후보를 score(=sim + cue 시 TAG_KEYWORD_BONUS) 내림차순 top-k(TAG_TOP_K)
    후보 0개 → 태그 0 = 항목 부재(부정 증거 후보, §9)
고정밀 cue(처럼·되셨어요 등)는 floor 를 낮춰(TAG_FLOOR_KW) 저sim 진짜 인스턴스를 살리고,
가산점으로 generic 임베딩 FP 위로 끌어올린다. 동음이의 키워드는 checklist 에서 이미 제외.

대상 = taggable_items()(국소/도입/종료). metric·global 은 chunk 태깅 안 함(§5).
도입/종료 항목은 강의 앞/뒤 위치 chunk 에만 적용. 임베딩 1패스를 분할과 공유(folding).
상호작용 항목(C5)의 톤·문맥 판단은 후보만 잡고, 확정은 ⑥ 분석의 문맥 LLM 단계(readme_V1).
"""
from __future__ import annotations

import numpy as np

from src import config
from src.analyze.checklist import ITEM_EXEMPLARS, taggable_items
from src.refine.embedding import cosine_matrix


def keyword_hits(text: str, seeds: list[str]) -> list[str]:
    return [kw for kw in seeds if kw and kw in text]


def tag_chunks(chunks: list[dict], embed_fn, top_k: int = None,
               floor: float = None, floor_kw: float = None) -> list[dict]:
    """각 chunk 에 eval_tags 부착(항목당 top-k 검색). 같은 강의 단위 리스트.

    chunk 필요 필드: clean_text, (chunk_emb 없으면 여기서 계산), pos(0~1 위치).
    반환: 같은 리스트(각 dict 에 "eval_tags" 추가, score 내림차순).
    """
    top_k = config.TAG_TOP_K if top_k is None else top_k
    floor = config.TAG_RETRIEVE_FLOOR if floor is None else floor
    floor_kw = config.TAG_FLOOR_KW if floor_kw is None else floor_kw
    items = taggable_items()
    if not chunks:
        return chunks

    # 항목 임베딩(태깅 쿼리) — exemplar(실제 발화 예시) 평균. 없으면 description 폴백.
    # 추상 description 보다 구어체 청크와 변별력이 큼(§ITEM_EXEMPLARS, A/B +71%).
    q_texts, q_spans = [], []
    for it in items:
        ex = ITEM_EXEMPLARS.get(it["key"]) or [it["description"]]
        q_spans.append((len(q_texts), len(q_texts) + len(ex)))
        q_texts.extend(ex)
    q_emb = embed_fn(q_texts)                                    # [sum_k, d]
    item_emb = np.stack([q_emb[s:e].mean(0) for s, e in q_spans])
    item_emb = item_emb / (np.linalg.norm(item_emb, axis=1, keepdims=True) + 1e-9)
    # chunk 임베딩(없으면 clean_text로)
    if "chunk_emb" in chunks[0]:
        ch_emb = np.asarray([c["chunk_emb"] for c in chunks], dtype=np.float32)
    else:
        ch_emb = embed_fn([c["clean_text"] for c in chunks])
    sims = cosine_matrix(ch_emb, item_emb)                       # [n_chunks, m]

    n = len(chunks)
    for ch in chunks:
        ch["eval_tags"] = []
    positions = [ch.get("pos", (ci + 0.5) / n) for ci, ch in enumerate(chunks)]

    # 항목(=쿼리)마다 관련 청크 top-k 검색
    for mi, it in enumerate(items):
        cand = []
        for ci, ch in enumerate(chunks):
            pos, is_first, is_last = positions[ci], ci == 0, ci == n - 1
            # 도입/종료 항목 위치 게이트(첫/마지막 청크는 항상 허용)
            if it["eval_type"] == "intro" and not (pos <= config.INTRO_RATIO or is_first):
                continue
            if it["eval_type"] == "outro" and not (pos >= 1 - config.OUTRO_RATIO or is_last):
                continue
            sim = float(sims[ci, mi])
            hits = keyword_hits(ch["clean_text"], it["seed_keywords"])
            # cue 있으면 낮은 floor 로 구제(저sim 진짜 인스턴스 살림), 없으면 일반 floor
            if sim < (floor_kw if hits else floor):
                continue
            score = sim + (config.TAG_KEYWORD_BONUS if hits else 0.0)
            cand.append((ci, sim, score, hits[0] if hits else None))
        cand.sort(key=lambda x: -x[2])    # score 내림차순
        for ci, sim, score, cue in cand[:top_k]:
            chunks[ci]["eval_tags"].append({
                "item_key": it["key"], "sim": round(sim, 3),
                "score": round(score, 3), "cue": cue,
            })

    for ch in chunks:
        ch["eval_tags"].sort(key=lambda t: -t["score"])
    return chunks


def coverage(chunks: list[dict]) -> dict[str, int]:
    """항목별 태깅된 chunk 수(0 = 부정 증거 후보 — §9)."""
    cov: dict[str, int] = {it["key"]: 0 for it in taggable_items()}
    for ch in chunks:
        for t in ch.get("eval_tags", []):
            cov[t["item_key"]] = cov.get(t["item_key"], 0) + 1
    return cov
