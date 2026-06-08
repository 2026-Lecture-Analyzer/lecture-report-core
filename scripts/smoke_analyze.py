"""⑥ 분석 엔진 배관 스모크 (LLM 없이 stub judge). 라우팅·체크포인트·스키마만 검증.

사용법: python -m scripts.smoke_analyze
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analyze.engine import load_jsonl, run_analysis  # noqa: E402


def stub_judge(messages):
    """프롬프트 종류 무관하게 형식만 맞는 JSON 반환."""
    user = messages[-1]["content"]
    cid = 0
    for tok in user.split("[chunk ")[1:2]:
        cid = int(tok.split("]")[0]) if tok.split("]")[0].strip().isdigit() else 0
    return json.dumps({"score": 4, "verdict": "양호",
                       "evidence": [{"chunk_id": cid, "quote": "근거 인용"}],
                       "comment": "stub 평가", "needs_more": False}, ensure_ascii=False)


def main():
    tmp = Path(tempfile.mkdtemp())
    # 한 강의(2청크) — 일부 항목 태깅, 일부 미태깅(부정 증거)
    chunks = [
        {"chunk_id": 0, "date": "2026-02-02", "session": "오전", "file": "f.txt",
         "pos": 0.1, "clean_text": "오늘 배울 목표는 자바 입출력입니다. 스트림이란 데이터 흐름을 의미합니다.",
         "eval_tags": [{"item_key": "C2_objective", "sim": 0.6, "score": 0.7, "cue": "오늘"},
                       {"item_key": "C3_definition", "sim": 0.55, "score": 0.6, "cue": "의미"}]},
        {"chunk_id": 1, "date": "2026-02-02", "session": "오전", "file": "f.txt",
         "pos": 0.9, "clean_text": "정리하면 오늘 핵심은 스트림입니다. 직접 코드를 따라 해보세요.",
         "eval_tags": [{"item_key": "C2_summary", "sim": 0.5, "score": 0.55, "cue": "정리"},
                       {"item_key": "C4_practice", "sim": 0.52, "score": 0.62, "cue": "해보"}]},
    ]
    merged = [
        {"date": "2026-02-02", "session": "오전", "text": "오늘 이제 배울 목표는 막 자바입니다",
         "start_sec": 0, "end_sec": 30},
        {"date": "2026-02-02", "session": "오전", "text": "정리하면 스트림이고 그래서 끝입니다",
         "start_sec": 30, "end_sec": 60},
    ]
    cp = tmp / "chunks.jsonl"
    cp.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")
    mp = tmp / "merged.jsonl"
    mp.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in merged), encoding="utf-8")
    out = tmp / "analysis.jsonl"

    r1 = run_analysis(cp, stub_judge, out, merged_path=mp)
    print("1차:", r1)
    r2 = run_analysis(cp, stub_judge, out, merged_path=mp)   # 재개 — 전부 skip
    print("2차(재개):", r2)
    assert r2["new_rows"] == 0 and r2["skipped"] == 18, "재개 동작 오류"

    rows = load_jsonl(out)
    assert len(rows) == 18, f"항목 18개 아님: {len(rows)}"
    keys = {r["item_key"] for r in rows}
    from src.analyze.checklist import CHECKLIST
    assert keys == {it["key"] for it in CHECKLIST}, "항목 누락"
    # metric 항목은 metric 필드, 부정증거 항목은 negative_evidence
    pace = next(r for r in rows if r["item_key"] == "C3_pace")
    assert pace["metric"] and pace["eval_type"] == "metric", "지표형 채점 오류"
    review = next(r for r in rows if r["item_key"] == "C2_review")
    assert review["routing"]["negative_evidence"], "부정 증거 미표시(C2_review 태그 없음)"
    obj = next(r for r in rows if r["item_key"] == "C2_objective")
    assert obj["score"] == 4 and obj["evidence"], "LLM judge 결과 매핑 오류"

    by_type = {}
    for r in rows:
        by_type[r["eval_type"]] = by_type.get(r["eval_type"], 0) + 1
    print("유형별 항목수:", by_type)
    print(f"\n✅ 통과 — 18항목 평가, 라우팅(metric/intro/outro/local/global)·재개·부정증거·스키마 정상")


if __name__ == "__main__":
    main()
