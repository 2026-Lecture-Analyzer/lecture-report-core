"""한국어 임베딩 (KURE) — 토픽 분할(§5)·항목 태깅(§9) 공용.

문헌(TreeSeg/TextTiling·RubricRAG) 근거로 임베딩 기반을 메인으로 채택.
모델은 KURE(한국어 검색 특화). sentence-transformers 필요 → Colab/로컬 설치.

파이프라인 로직은 `embed_fn(list[str]) -> np.ndarray[n, d]` 주입으로 분리해,
모델 없이도 stub 임베더로 검증 가능(scripts/smoke_chunk_embed.py).
"""
from __future__ import annotations

import numpy as np

from src import config


def load_embedder(model_id: str = None):
    """KURE SentenceTransformer 로드(GPU 있으면 자동 사용)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_id or config.EMBED_MODEL_ID)


def make_embed_fn(model, batch_size: int = 64):
    """texts -> L2 정규화된 임베딩 행렬(np.ndarray[n, d])."""
    def embed_fn(texts: list[str]) -> np.ndarray:
        return np.asarray(model.encode(
            list(texts), batch_size=batch_size,
            normalize_embeddings=True, show_progress_bar=False,
        ), dtype=np.float32)
    return embed_fn


def cosine_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """행 단위 코사인 유사도 행렬. a,b 가 L2 정규화면 내적과 동일."""
    a = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    b = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return a @ b.T
