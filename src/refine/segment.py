"""임베딩 기반 토픽 분할 (TextTiling-lite) — Step 5 청킹의 핵심.

정제된 텍스트를 문장으로 쪼개 임베딩하고, 인접 문장 유사도의 '골(depth)'에서
주제 경계를 찾는다. (LLM 분할 대비 싸고 일관적 — §11 근거)
embed_fn 주입이라 모델 없이 stub 로 검증 가능.
"""
from __future__ import annotations

import re

import numpy as np

from src import config
from src.refine.embedding import cosine_matrix

# 한국어 문장 분리: 종결어미/문장부호 뒤에서 분할(간이).
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+|(?<=[다요죠])\s+(?=[A-Z가-힣])")


def split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_SPLIT.split(text or "") if s and s.strip()]
    return parts


def _depth_scores(sims: np.ndarray) -> np.ndarray:
    """각 gap(i, i+1)의 TextTiling depth = (왼쪽 peak - sim) + (오른쪽 peak - sim)."""
    n = len(sims)
    depth = np.zeros(n)
    for i in range(n):
        l = sims[i]
        j = i
        while j > 0 and sims[j - 1] >= sims[j]:
            j -= 1
            l = max(l, sims[j])
        r = sims[i]
        j = i
        while j < n - 1 and sims[j + 1] >= sims[j]:
            j += 1
            r = max(r, sims[j])
        depth[i] = (l - sims[i]) + (r - sims[i])
    return depth


def segment_sentences(sentences: list[str], embed_fn=None,
                      depth_c: float = None, min_sents: int = None,
                      max_sents: int = None, emb: np.ndarray = None) -> list[list[int]]:
    """문장 리스트 → 청크(문장 인덱스 그룹) 리스트.

    emb: 사전 계산된 문장 임베딩(태깅과 공유해 재임베딩 방지). 없으면 embed_fn 사용.
    반환: [[0,1,2], [3,4], ...]
    """
    depth_c = config.SEG_DEPTH_C if depth_c is None else depth_c
    min_sents = config.SEG_MIN_SENTS if min_sents is None else min_sents
    max_sents = config.SEG_MAX_SENTS if max_sents is None else max_sents

    n = len(sentences)
    if n <= min_sents:
        return [list(range(n))] if n else []

    emb = embed_fn(sentences) if emb is None else emb   # [n, d]
    adj = cosine_matrix(emb[:-1], emb[1:]).diagonal()  # gap별 인접 유사도 [n-1]
    depth = _depth_scores(adj)
    thr = depth.mean() + depth_c * depth.std()
    # 경계 후보: depth가 임계 초과인 gap (i 다음에서 끊음)
    boundaries = {i + 1 for i in range(len(depth)) if depth[i] > thr}

    chunks, cur = [], []
    for idx in range(n):
        cur.append(idx)
        end = (idx + 1) in boundaries or (idx == n - 1)
        too_big = len(cur) >= max_sents
        if (end and len(cur) >= min_sents) or too_big:
            chunks.append(cur)
            cur = []
    if cur:  # 남은 짧은 꼬리는 직전 청크에 흡수
        if chunks:
            chunks[-1].extend(cur)
        else:
            chunks.append(cur)
    return chunks
