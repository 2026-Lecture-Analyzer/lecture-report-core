"""⑦ 스코어링 스모크 — 항목가중·정규화·N/A 제외·부정증거를 코드로 고정.

사용법: python -m scripts.smoke_score
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analyze.checklist import WEIGHT_VALUE, by_key  # noqa: E402
from src.scoring.scoring import compute_scores, score_lecture  # noqa: E402


def main():
    it = by_key()
    # 한 강의: C1 3항목 중 1개 N/A, C5_check 부정증거
    rows = [
        {"lecture_id": "L", "date": "2026-02-02", "session": "오전",
         "item_key": "C1_repetition", "category": "C1", "score": None, "routing": {}},
        {"lecture_id": "L", "date": "2026-02-02", "session": "오전",
         "item_key": "C1_completeness", "category": "C1", "score": 5, "routing": {}},
        {"lecture_id": "L", "date": "2026-02-02", "session": "오전",
         "item_key": "C1_consistency", "category": "C1", "score": 3, "routing": {}},
        {"lecture_id": "L", "date": "2026-02-02", "session": "오전",
         "item_key": "C5_check", "category": "C5", "score": 1,
         "routing": {"negative_evidence": True}},
    ]
    r = score_lecture(rows)

    # 수동 검산: C1 = (norm100*w_comp + norm50*w_cons)/(w_comp+w_cons), repetition N/A 제외
    wc = WEIGHT_VALUE[it["C1_completeness"]["weight"]]
    wco = WEIGHT_VALUE[it["C1_consistency"]["weight"]]
    c1 = round((100 * wc + 50 * wco) / (wc + wco), 1)
    assert r["category_scores"]["C1"] == c1, f"C1 가중 오류: {r['category_scores']['C1']} != {c1}"
    assert r["n_na"] == 1, "N/A 카운트 오류"
    assert next(d for d in r["items"] if d["item_key"] == "C1_repetition")["norm"] is None, "N/A norm 오류"
    assert next(d for d in r["items"] if d["item_key"] == "C5_check")["negative"], "부정증거 플래그 오류"

    # 종합 = 전 항목(N/A 제외) 가중평균
    wcheck = WEIGHT_VALUE[it["C5_check"]["weight"]]
    tot = round((100 * wc + 50 * wco + 0 * wcheck) / (wc + wco + wcheck), 1)
    assert r["total_score"] == tot, f"종합 가중 오류: {r['total_score']} != {tot}"

    # 2강의 요약(추이)
    rows2 = [dict(x, lecture_id="M", date="2026-02-03") for x in rows]
    sc = compute_scores(rows + rows2)
    assert sc["summary"]["n_lectures"] == 2, "강의 수 오류"
    assert set(sc["summary"]["by_date"]) == {"2026-02-02", "2026-02-03"}, "추이 일자 오류"

    print(f"C1(N/A 제외)={r['category_scores']['C1']} · 종합={r['total_score']} · n_na={r['n_na']}")
    print(f"요약 추이: {sc['summary']['by_date']}")
    print("\n✅ 통과 — 항목가중·정규화·N/A 제외·부정증거·추이 정상")


if __name__ == "__main__":
    main()
