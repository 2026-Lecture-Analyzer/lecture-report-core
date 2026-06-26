"""한국어 임베딩 — 토픽 분할(§5)·항목 태깅(§9) 공용. 백엔드 2종.

  "kure"    : nlpai-lab/KURE-v1 (sentence-transformers) — 품질 1순위(§11), GPU 권장·CPU 가능
  "upstage" : Upstage 임베딩 API(OpenAI 호환) — 다운로드·GPU 불필요, UPSTAGE_API_KEY

문헌(TreeSeg/TextTiling·RubricRAG) 근거로 임베딩 기반을 메인으로 채택.
두 백엔드 모두 `embed_fn(list[str]) -> np.ndarray[n, d]`(L2 정규화) 동일 인터페이스라
segment/tagging/chunk_embed 코드는 백엔드를 몰라도 된다. 디스패처: make_embedder_fn().
모델 없이도 stub 임베더로 검증 가능(scripts/smoke_chunk_embed.py).
"""
from __future__ import annotations

import os

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


# ── Upstage 임베딩 API 백엔드 (OpenAI 호환) ─────────────────────────────
def make_upstage_embed_fn(api_key: str = None, model: str = None,
                          base_url: str = None, batch_size: int = 100):
    """Upstage 임베딩 API embed_fn. texts -> L2 정규화 np.ndarray[n, d].

    키: 인자 > 환경변수 UPSTAGE_API_KEY(.env 자동 로드). 다운로드·GPU 불필요.
    입력은 batch_size 단위로 쪼개 호출(요청당 입력 수 제한 대응).
    """
    from openai import OpenAI

    api_key = api_key or os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "UPSTAGE_API_KEY 가 없습니다. .env 에 UPSTAGE_API_KEY=... 를 넣거나 "
            "환경변수로 export 하세요(Colab: getpass 로 주입)."
        )
    client = OpenAI(api_key=api_key, base_url=base_url or config.UPSTAGE_BASE_URL)
    model = model or config.UPSTAGE_EMBED_MODEL

    def embed_fn(texts: list[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        vecs: list = []
        for i in range(0, len(texts), batch_size):
            resp = client.embeddings.create(model=model, input=texts[i:i + batch_size])
            vecs.extend(d.embedding for d in resp.data)
        arr = np.asarray(vecs, dtype=np.float32)
        arr /= (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)
        return arr

    return embed_fn


# ── Google Gemini 임베딩 백엔드 (google-genai SDK) ──────────────────────
def make_google_embed_fn(api_key: str = None, model: str = None,
                         batch_size: int = 100, dim: int = None):
    """Google Gemini 임베딩 embed_fn. texts -> L2 정규화 np.ndarray[n, d].

    키: 인자 > 환경변수 GOOGLE_API_KEY(.env 자동 로드). 다운로드·GPU 불필요.
    dim 지정 시 output_dimensionality 축소(축소하면 재정규화 권장 → 여기서 L2 처리).
    입력은 batch_size 단위로 쪼개 호출(요청당 입력 수 제한 대응).
    """
    from google import genai
    from google.genai import types

    api_key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY 가 없습니다. .env 에 GOOGLE_API_KEY=... 를 넣거나 "
            "환경변수로 export 하세요(https://aistudio.google.com/apikey)."
        )
    client = genai.Client(api_key=api_key)
    model = model or config.GOOGLE_EMBED_MODEL
    dim = dim if dim is not None else config.GOOGLE_EMBED_DIM

    def embed_fn(texts: list[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        cfg = types.EmbedContentConfig(output_dimensionality=dim) if dim else None
        vecs: list = []
        for i in range(0, len(texts), batch_size):
            resp = client.models.embed_content(
                model=model, contents=texts[i:i + batch_size], config=cfg)
            vecs.extend(e.values for e in resp.embeddings)
        arr = np.asarray(vecs, dtype=np.float32)
        arr /= (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)
        return arr

    return embed_fn


def make_embedder_fn(backend: str = None, **kwargs):
    """임베딩 백엔드 디스패처 — config.EMBED_BACKEND 기본.

    "upstage" → make_upstage_embed_fn(**kwargs)
    "google"  → make_google_embed_fn(**kwargs)
    "kure"    → make_embed_fn(load_embedder()) (kwargs 무시, ~2GB 다운로드)
    """
    backend = backend or config.EMBED_BACKEND
    if backend == "upstage":
        return make_upstage_embed_fn(**kwargs)
    if backend == "google":
        return make_google_embed_fn(**kwargs)
    if backend == "kure":
        return make_embed_fn(load_embedder())
    raise ValueError(f"알 수 없는 EMBED_BACKEND: {backend!r} (kure|upstage|google)")
