"""Solar-10.7B 로더 + generate_fn (Colab/GPU 전용).

로컬(CPU)에서는 transformers/torch 미설치이거나 모델이 너무 커서 못 돌린다.
파이프라인 로직은 generate_fn 주입으로 분리돼 있어, 로컬 테스트는 stub 으로 한다.
Colab(A100)에서는 아래 load_solar() → make_generate_fn() 으로 실제 함수를 주입한다.

재현성: revision 핀(config.MODEL_REVISION), 그리디 디코딩, 시드 고정.
"""
from __future__ import annotations

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
