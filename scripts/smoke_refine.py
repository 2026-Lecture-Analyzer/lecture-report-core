"""Step 3~5 파이프라인 배관 스모크 테스트 (모델 없이, GPU 불필요).

stub generate_fn 을 주입해 섹션화·정제·체크포인트 재개·청킹 로직이 정상 동작하는지
확인한다. 실제 모델 품질이 아니라 '플럼빙'만 검증한다(Colab 전 사전 점검용).

사용법: python -m scripts.smoke_refine
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.refine import refine as refine_mod  # noqa: E402
from src.refine.chunk import run_chunk  # noqa: E402
from src.refine.glossary import SEED_GLOSSARY  # noqa: E402
from src.refine.sectionize import load_merged, make_sections  # noqa: E402

_FILLERS = ["이제 ", "저희가 ", "그다음에 ", " 막 ", " 뭐 ", "자 ", "어 ", "음 "]


def stub_generate_fn(messages: list[dict]) -> str:
    """프롬프트 종류를 감지해 형식만 맞는 JSON 을 돌려주는 가짜 모델."""
    sys_c = messages[0]["content"]
    user_c = messages[-1]["content"]
    if "교정" in sys_c:  # glossary
        return '{"corrections": [{"wrong": "셀렉", "correct": "SELECT"}], "terms": ["테이블"]}'
    if "편집자" in sys_c:  # refine
        body = user_c.split("[정제할 섹션 원문]\n", 1)[-1].split("\n\n위 섹션", 1)[0]
        body = re.sub(r"\[[^\]]+\]\s*", "", body)  # 역할 태그 제거
        for f in _FILLERS:
            body = body.replace(f, "")
        body = re.sub(r"\s+", " ", body).strip()
        return json.dumps({"clean_text": body, "summary": "이 섹션 요약(stub)."},
                          ensure_ascii=False)
    if "분할" in sys_c:  # chunk
        body = user_c.split("---\n", 1)[-1].rsplit("\n---", 1)[0]
        half = len(body) // 2
        cut = body.find(" ", half)
        cut = cut if cut > 0 else half
        return json.dumps({"chunks": [
            {"topic": "전반부", "text": body[:cut].strip()},
            {"topic": "후반부", "text": body[cut:].strip()},
        ]}, ensure_ascii=False)
    return "{}"


def main():
    merged = load_merged(config.PROCESSED_DIR / "merged.jsonl")[:12]
    sections = make_sections(merged)
    print(f"블록 {len(merged)} → 섹션 {len(sections)}개")

    tmp = config.PROCESSED_DIR / "_smoke"
    tmp.mkdir(parents=True, exist_ok=True)
    clean_path = tmp / "clean.jsonl"
    chunks_path = tmp / "chunks.jsonl"
    for p in (clean_path, chunks_path):
        p.unlink(missing_ok=True)

    # 1차 정제: 앞 절반만 처리해 체크포인트 만들기
    half = sections[: len(sections) // 2 or 1]
    r1 = refine_mod.run_refine(half, dict(SEED_GLOSSARY), stub_generate_fn, clean_path)
    print("1차 정제:", r1)
    # 2차: 전체 → 앞부분은 resume 로 skip 되어야 함
    r2 = refine_mod.run_refine(sections, dict(SEED_GLOSSARY), stub_generate_fn, clean_path)
    print("2차 정제(재개):", r2)
    assert r2["skipped"] == len(half), "재개 skip 개수 불일치"

    rc = run_chunk(clean_path, stub_generate_fn, chunks_path)
    print("청킹:", rc)

    # 검증: 추적성 raw_ref 보존
    clean = [json.loads(l) for l in clean_path.open(encoding="utf-8")]
    chunks = [json.loads(l) for l in chunks_path.open(encoding="utf-8")]
    assert all(c["raw_ref"] for c in clean), "clean raw_ref 누락"
    assert all(c["raw_ref"] for c in chunks), "chunk raw_ref 누락"
    assert "잡바" not in "".join(c["clean_text"] for c in clean), "rule 치환(잡바→Java) 미적용"
    print(f"\n✅ 통과 — clean {len(clean)}건, chunks {len(chunks)}건, raw_ref 추적성 유지, rule 치환 적용")
    print("샘플 chunk:", json.dumps(chunks[0], ensure_ascii=False)[:200])


if __name__ == "__main__":
    main()
