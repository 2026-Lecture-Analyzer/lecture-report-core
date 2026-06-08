"""임베딩 청킹·태깅·개요 배관 스모크 테스트 (KURE 없이 stub 임베더로).

실제 임베딩 품질이 아니라 '플럼빙'(분할→태깅→추적성→위치게이트)만 검증.
주의: stub 임베더는 의미가 아니라 어휘 기반이라 dense 유사도가 낮다. 하이브리드 태깅
규칙(dense 주신호)을 배관 수준에서 통과시키려고 아래에서 태깅 임계를 낮춘다(품질 X·배관 O).
사용법: python -m scripts.smoke_chunk_embed
"""
import json
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.refine.chunk_embed import run_chunk_embed  # noqa: E402
from src.refine.overview import build_overview, extract_keywords  # noqa: E402
from src.refine.tagging import coverage  # noqa: E402

# stub(어휘) 임베더용 임계 완화 — 실제 KURE/Upstage는 config 기본값(0.45/0.30) 사용.
config.TAG_SIM_THRESHOLD = 0.05
config.TAG_SIM_THRESHOLD_KW = 0.0


def stub_embed_fn(texts):
    """결정적 bag-of-words 임베딩(같은 단어 공유 → 높은 코사인)."""
    dim = 512
    vecs = []
    for t in texts:
        v = np.zeros(dim, dtype=np.float32)
        for w in re.findall(r"[가-힣A-Za-z0-9]+", t):
            v[hash(w) % dim] += 1.0
        nrm = np.linalg.norm(v)
        vecs.append(v / nrm if nrm else v)
    return np.asarray(vecs, dtype=np.float32)


# cue 단어를 곳곳에 심은 가짜 정제 섹션(한 강의)
SECTION_A = ("오늘 배울 목표는 자바 입출력입니다 진행 순서를 안내하겠습니다. "
             "지난 시간 복습부터 하겠습니다 어제 배운 스트림을 떠올려보세요. "
             "스트림이란 데이터의 흐름을 의미합니다 핵심 개념이니 꼭 기억하세요. "
             "예를 들어 파일을 읽는 것은 마치 물을 따르는 것과 같습니다.")
SECTION_B = ("이제 실습으로 직접 코드를 따라 쳐보겠습니다 같이 해볼까요. "
             "여기서 오류가 나면 빨간 줄을 보고 에러를 고칩니다. "
             "되셨어요 이해하셨나요 맞죠 확인하고 넘어가겠습니다. "
             "정리하면 오늘 배운 핵심은 스트림과 입출력이었습니다 요약 마무리합니다.")


def main():
    tmp = Path(tempfile.mkdtemp())
    clean = [
        {"section_id": 0, "file": "f.txt", "date": "2026-02-02", "session": "오전",
         "raw_ref": [0, 1, 2], "start_time": "09:00:00", "end_time": "09:20:00",
         "clean_text": SECTION_A},
        {"section_id": 1, "file": "f.txt", "date": "2026-02-02", "session": "오전",
         "raw_ref": [3, 4, 5], "start_time": "09:20:00", "end_time": "09:40:00",
         "clean_text": SECTION_B},
    ]
    cp = tmp / "clean.jsonl"
    cp.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in clean), encoding="utf-8")

    r = run_chunk_embed(cp, stub_embed_fn, tmp / "chunks.jsonl")
    print("청킹+태깅:", r)
    chunks = [json.loads(l) for l in (tmp / "chunks.jsonl").open(encoding="utf-8")]

    assert chunks, "청크 0개"
    assert all("eval_tags" in c for c in chunks), "eval_tags 누락"
    assert all(c["raw_ref"] for c in chunks), "raw_ref 추적성 누락"
    assert "chunk_emb" not in chunks[0], "임베딩이 직렬화에 남음"

    cov = coverage(chunks)
    tagged_items = {k for k, v in cov.items() if v > 0}
    print("태깅된 항목:", sorted(tagged_items))
    # cue 기반 최소 기대: 도입(목표/복습)·국소(정의/비유/실습/오류/이해확인)·종료(요약)
    for must in ["C2_objective", "C3_definition", "C4_practice", "C5_check", "C2_summary"]:
        assert must in tagged_items, f"{must} 태깅 실패"

    # 위치 게이트: 청크 2개 이상이면 objective(도입)이 summary(종료)보다 앞 chunk
    if len(chunks) > 1:
        obj_pos = min(c["pos"] for c in chunks
                      if any(t["item_key"] == "C2_objective" for t in c["eval_tags"]))
        sum_pos = max(c["pos"] for c in chunks
                      if any(t["item_key"] == "C2_summary" for t in c["eval_tags"]))
        assert obj_pos <= sum_pos, "도입이 종료보다 뒤에 위치(게이트 오류)"

    # 개요(키워드) — KoNLPy
    kws = extract_keywords([SECTION_A, SECTION_B])
    print("키워드 Top:", kws[:8])
    ov = build_overview([SECTION_A, SECTION_B],
                        generate_fn=lambda m: '{"outline": ["자바 입출력", "스트림 실습"]}')
    print("개요:", ov["outline"], "| 키워드수:", len(ov["keywords"]))

    print(f"\n✅ 통과 — chunks {len(chunks)}, 태깅항목 {len(tagged_items)}개, "
          f"raw_ref 추적·위치게이트·개요 정상")


if __name__ == "__main__":
    main()
