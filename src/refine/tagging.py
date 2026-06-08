"""평가항목 태깅(§9) — chunk 에 관련 평가항목(eval_tags) 다중 라벨 부착.

하이브리드 신호(문헌: RubricRAG=dense 검색, DAT=dense+키워드 가중):
  (1) **dense 임베딩 유사도**(chunk vs 항목 description) — 주 신호. 구어체 lexical gap 보완.
  (2) 시드 키워드 매칭 — 보조. 단독으론 약함(구어체에서 모호) → dense 임계를 낮춰주는 역할만.

태깅 규칙(키워드 단독·저유사도 오탐 방지):
    sim ≥ TAG_SIM_THRESHOLD                         (dense 단독으로 충분)
    OR (키워드 hit AND sim ≥ TAG_SIM_THRESHOLD_KW)  (키워드가 낮춘 임계 통과)
랭킹 score = sim + (키워드 hit 시 TAG_KEYWORD_BONUS).

대상 = taggable_items()(국소/도입/종료). metric·global 은 chunk 태깅 안 함(§5).
도입/종료 항목은 강의 앞/뒤 위치 chunk 에만 적용. 임베딩 1패스를 분할과 공유(folding).
상호작용 항목(C5)의 톤·문맥 판단은 여기서 후보만 잡고, 확정은 ⑥ 분석의 문맥 LLM 단계(readme_V1).
"""
from __future__ import annotations

import numpy as np

from src import config
from src.analyze.checklist import taggable_items
from src.refine.embedding import cosine_matrix


def keyword_hits(text: str, seeds: list[str]) -> list[str]:
    return [kw for kw in seeds if kw and kw in text]


def tag_chunks(chunks: list[dict], embed_fn,
               sim_threshold: float = None) -> list[dict]:
    """각 chunk 에 eval_tags 부착. chunks 는 같은 강의(파일·세션) 단위 리스트.

    chunk 필요 필드: clean_text, (chunk_emb 없으면 여기서 계산), pos(0~1 위치).
    반환: 같은 리스트(각 dict 에 "eval_tags" 추가).
    """
    sim_threshold = config.TAG_SIM_THRESHOLD if sim_threshold is None else sim_threshold
    items = taggable_items()
    if not chunks:
        return chunks

    # 항목 description 임베딩(태깅 대상만, 1회)
    item_emb = embed_fn([it["description"] for it in items])     # [m, d]
    # chunk 임베딩(없으면 clean_text로)
    if "chunk_emb" in chunks[0]:
        ch_emb = np.asarray([c["chunk_emb"] for c in chunks], dtype=np.float32)
    else:
        ch_emb = embed_fn([c["clean_text"] for c in chunks])
    sims = cosine_matrix(ch_emb, item_emb)                       # [n_chunks, m]

    n = len(chunks)
    for ci, ch in enumerate(chunks):
        pos = ch.get("pos", (ci + 0.5) / n)   # 강의 내 상대 위치 0~1
        is_first, is_last = (ci == 0), (ci == n - 1)
        tags = []
        for mi, it in enumerate(items):
            # 도입/종료 항목 위치 게이트 (첫/마지막 청크는 항상 허용 — 청크 수 적을 때 robust)
            if it["eval_type"] == "intro" and not (pos <= config.INTRO_RATIO or is_first):
                continue
            if it["eval_type"] == "outro" and not (pos >= 1 - config.OUTRO_RATIO or is_last):
                continue
            hits = keyword_hits(ch["clean_text"], it["seed_keywords"])
            sim = float(sims[ci, mi])
            # 하이브리드: dense 주 신호 + 키워드 가중 보조(키워드 단독·저유사도 오탐 방지)
            tagged = sim >= sim_threshold or (hits and sim >= config.TAG_SIM_THRESHOLD_KW)
            if tagged:
                score = sim + (config.TAG_KEYWORD_BONUS if hits else 0.0)
                tags.append({
                    "item_key": it["key"],
                    "sim": round(sim, 3),
                    "score": round(score, 3),
                    "cue": hits[0] if hits else None,
                })
        ch["eval_tags"] = sorted(tags, key=lambda t: -t["score"])
    return chunks


def coverage(chunks: list[dict]) -> dict[str, int]:
    """항목별 태깅된 chunk 수(0 = 부정 증거 후보 — §9)."""
    cov: dict[str, int] = {it["key"]: 0 for it in taggable_items()}
    for ch in chunks:
        for t in ch.get("eval_tags", []):
            cov[t["item_key"]] = cov.get(t["item_key"], 0) + 1
    return cov
