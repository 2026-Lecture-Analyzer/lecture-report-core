"""Solar generate_fn — 백엔드 2종 (config.MODEL_BACKEND 로 분기).

  "hf"      : HuggingFace 오픈모델(SOLAR-10.7B-Instruct) — Colab A100, load_solar()+make_generate_fn()
  "upstage" : Upstage Solar API(OpenAI 호환) — make_upstage_generate_fn(), GPU 불필요(로컬 가능)

두 백엔드 모두 동일한 generate_fn(messages: list[dict]) -> str 인터페이스라,
refine/glossary/chunk 파이프라인 코드는 백엔드를 몰라도 된다.
편의 디스패처: make_solar_generate_fn(backend=None).

재현성: hf=그리디·시드 고정 / upstage=temperature=0. 모델 revision/버전 핀 권장.
"""
from __future__ import annotations

import os

from src import config


def set_seed(seed: int = None) -> None:
    seed = config.SEED if seed is None else seed
    import random

    import numpy as np
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_solar(model_id: str = None, revision: str = None):
    """토크나이저+모델 로드. A100 40GB 기준 fp16 권장."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id = model_id or config.MODEL_ID
    revision = revision if revision is not None else config.MODEL_REVISION
    set_seed()

    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, revision=revision,
        torch_dtype=torch.float16, device_map="auto",
    )
    model.eval()
    return model, tokenizer


def make_generate_fn(model, tokenizer, max_new_tokens: int = None):
    """messages(list[dict]) → 생성 문자열. 그리디(결정적) 디코딩."""
    import torch
    max_new_tokens = max_new_tokens or config.GEN_MAX_NEW_TOKENS

    def generate_fn(messages: list[dict]) -> str:
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs, max_new_tokens=max_new_tokens,
                do_sample=config.GEN_DO_SAMPLE,
                pad_token_id=tokenizer.eos_token_id,
            )
        gen = out[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(gen, skip_special_tokens=True)

    return generate_fn


# ── Upstage Solar API 백엔드 (OpenAI 호환) ──────────────────────────────
def make_upstage_generate_fn(api_key: str = None, model: str = None,
                             base_url: str = None, max_tokens: int = None,
                             temperature: float = 0):
    """Upstage Solar API 호출 generate_fn. messages 는 OpenAI chat 포맷 그대로.

    키: 인자 > 환경변수 UPSTAGE_API_KEY(.env 자동 로드). 기본 temperature=0(결정적).
    self-consistency(다수결) 용으로 temperature>0 을 주면 샘플 다양성이 생긴다.
    GPU 불필요 → 로컬에서도 정제 파이프라인을 끝까지 돌릴 수 있다.
    """
    from openai import OpenAI

    api_key = api_key or os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "UPSTAGE_API_KEY 가 없습니다. .env 에 UPSTAGE_API_KEY=... 를 넣거나 "
            "환경변수로 export 하세요(Colab: getpass 로 주입)."
        )
    client = OpenAI(api_key=api_key, base_url=base_url or config.UPSTAGE_BASE_URL)
    model = model or config.UPSTAGE_MODEL
    max_tokens = max_tokens or config.GEN_MAX_NEW_TOKENS

    def generate_fn(messages: list[dict]) -> str:
        resp = client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    return generate_fn


# ── Google Gemini API 백엔드 (google-genai SDK) ─────────────────────────
def _to_gemini_contents(messages: list[dict]):
    """OpenAI chat messages → (system_instruction, contents) for google-genai.

    Gemini 는 'assistant' 대신 'model' 롤을 쓰고 system 은 별도 필드라,
    system 메시지는 system_instruction 으로 분리하고 나머지를 user/model 로 매핑한다.
    """
    from google.genai import types

    sys_parts: list[str] = []
    contents: list = []
    for m in messages:
        text = m.get("content") or ""
        if m.get("role") == "system":
            sys_parts.append(text)
        else:
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    if not contents:   # system 만 있으면 Gemini 가 빈 입력을 거부 → user 로 전환
        contents = [types.Content(role="user", parts=[types.Part(text="\n".join(sys_parts))])]
        sys_parts = []
    return "\n".join(sys_parts), contents


def make_google_generate_fn(api_key: str = None, model: str = None,
                            max_tokens: int = None, temperature: float = 0):
    """Google Gemini API 호출 generate_fn. Upstage 와 동일한 messages 인터페이스.

    키: 인자 > 환경변수 GOOGLE_API_KEY(.env 자동 로드). 기본 temperature=0(결정적).
    self-consistency(다수결) 용으로 temperature>0 을 주면 샘플 다양성이 생긴다.
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
    model = model or config.GOOGLE_MODEL
    max_tokens = max_tokens or config.GEN_MAX_NEW_TOKENS

    # gemini-2.5 thinking 처리: flash 는 기본 thinking 이 max_output_tokens 를 소진해
    # 구조화 출력이 잘림 → thinking_budget=0 으로 끈다. pro 는 thinking 필수라 끄면 400 →
    # 그대로 두고(기본) 추론+출력이 함께 들어가게 max_tokens 를 넉넉히 확보한다.
    think_cfg = None
    if "flash" in (model or ""):
        try:
            think_cfg = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            think_cfg = None
    else:                                   # pro 등 thinking 필수 모델 — 출력 여유 확보
        max_tokens = max(max_tokens, 24000)

    def generate_fn(messages: list[dict]) -> str:
        system, contents = _to_gemini_contents(messages)
        resp = client.models.generate_content(
            model=model, contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system or None,
                temperature=temperature,
                max_output_tokens=max_tokens,
                thinking_config=think_cfg,
            ),
        )
        try:
            return resp.text or ""
        except Exception:   # 안전필터·빈 응답 등으로 .text 접근 실패 시 빈 문자열(상위에서 흡수)
            return ""

    return generate_fn


def make_solar_generate_fn(backend: str = None, **kwargs):
    """백엔드 디스패처 — config.MODEL_BACKEND 기본.

    "upstage" → make_upstage_generate_fn(**kwargs)
    "google"  → make_google_generate_fn(**kwargs)
    "hf"      → load_solar() 후 make_generate_fn() (kwargs 무시, GPU 필요)
    """
    from src.governor import govern        # 전역 호출 거버너(분당상한·총예산·동시성)
    backend = backend or config.MODEL_BACKEND
    if backend == "upstage":
        fn = make_upstage_generate_fn(**kwargs)
    elif backend == "google":
        fn = make_google_generate_fn(**kwargs)
    elif backend == "hf":
        model, tokenizer = load_solar()
        fn = make_generate_fn(model, tokenizer)
    else:
        raise ValueError(f"알 수 없는 MODEL_BACKEND: {backend!r} (hf|upstage|google)")
    return govern(fn)
