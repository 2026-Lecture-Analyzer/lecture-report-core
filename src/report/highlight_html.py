"""대시보드 ②탭 근거 하이라이트 보조 — evidence 인용문 ↔ chunk_id 역매핑.

분석/holistic 단계는 evidence에 chunk_id를 안 남기므로(quote·time만), 인용문이 어느 청크
clean_text에 들어있는지로 역매핑해야 hover 하이라이트가 동작한다. `dashboard.py`가 호출.
"""
from __future__ import annotations

import re


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def resolve_chunk_ids(items_data: list[dict], chunks: list[dict]) -> None:
    """evidence 인용문을 청크 본문과 대조해 chunk_id를 채운다(이미 있으면 유지).

    raw 발화 기반(메트릭·C5) 인용은 청크와 안 맞아 -1로 남고, 그 항목은 dimming만 된다.
    """
    chn = [(c["chunk_id"], _norm(c.get("clean_text", ""))) for c in chunks]
    for item in items_data:
        for e in item.get("evidence") or []:
            cid = e.get("chunk_id")
            if cid is not None and cid >= 0:
                continue
            q = _norm(e.get("quote", ""))
            if len(q) < 5:
                continue
            key = q[:14]
            for cid2, ct in chn:
                if key in ct:
                    e["chunk_id"] = cid2
                    break
