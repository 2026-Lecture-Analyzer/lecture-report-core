"""STT 모델 어댑터 — 오디오 1청크를 받아 모델 전사 텍스트를 돌려주는 transcribe_fn.

refine 의 generate_fn 주입 패턴과 동일: 파이프라인 로직(transcribe.py)은 모델을 모른 채
transcribe_fn(audio_path, messages)->str 만 호출 → GPU·키·오디오 없이 stub 로 배관 검증.

현재 backend=google(Gemini 오디오 네이티브)만 구현. Files API 로 오디오를 올리고
시스템+유저 프롬프트와 함께 generate_content 호출.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from src import config


def _split_sys(messages: list[dict]) -> tuple[str, str]:
    """messages → (system, user) 텍스트로 단순 분해(STT 는 2턴 고정)."""
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    user = "\n".join(m["content"] for m in messages if m.get("role") != "system")
    return system.strip(), user.strip()


def make_gemini_transcribe_fn(api_key: str = None, model: str = None,
                              max_tokens: int = None, temperature: float = 0):
    """Gemini 오디오 전사 transcribe_fn 생성.

    키: 인자 > 환경변수 GOOGLE_API_KEY(.env). 기본 temperature=0(결정적 전사).
    """
    from google import genai
    from google.genai import types

    api_key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY 가 없습니다. .env 에 GOOGLE_API_KEY=... 를 넣거나 환경변수로 "
            "export 하세요(https://aistudio.google.com/apikey)."
        )
    client = genai.Client(api_key=api_key)
    model = model or config.STT_MODEL
    max_tokens = max_tokens or config.STT_MAX_TOKENS
    # flash 는 thinking 이 출력 토큰을 소진해 전사가 잘림 → 끈다(refine 와 동일 처리).
    think_cfg = types.ThinkingConfig(thinking_budget=0) if "flash" in model else None

    def _upload_active(path: Path):
        """Files API 업로드 후 ACTIVE 될 때까지 잠깐 대기(오디오는 보통 즉시)."""
        f = client.files.upload(file=str(path))
        for _ in range(30):
            state = getattr(getattr(f, "state", None), "name", None) or getattr(f, "state", None)
            if state in ("ACTIVE", None):
                return f
            if state == "FAILED":
                raise RuntimeError(f"오디오 업로드 처리 실패: {path}")
            time.sleep(1)
            f = client.files.get(name=f.name)
        return f

    def transcribe_fn(audio_path: Path, messages: list[dict]) -> str:
        system, user = _split_sys(messages)
        uploaded = _upload_active(Path(audio_path))
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[user, uploaded],
                config=types.GenerateContentConfig(
                    system_instruction=system or None,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    thinking_config=think_cfg,
                ),
            )
            try:
                return resp.text or ""
            except Exception:
                return ""
        finally:
            try:
                client.files.delete(name=uploaded.name)   # 업로드 정리(쿼터 절약)
            except Exception:
                pass

    return transcribe_fn


def make_transcribe_fn(backend: str = None, **kwargs):
    """백엔드 디스패처 — config.STT_BACKEND 기본. 현재 google 만. 전역 거버너 통과."""
    from src.governor import govern
    backend = backend or config.STT_BACKEND
    if backend == "google":
        return govern(make_gemini_transcribe_fn(**kwargs))
    raise ValueError(f"지원하지 않는 STT_BACKEND: {backend!r} (현재 'google'만)")
