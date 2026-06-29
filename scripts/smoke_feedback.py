"""피드백 상관분석 스모크 — 외부데이터 없이 생성·상관·리포트 검증.

핵심: 샘플 생성이 (1) 재현 가능 (2) driver 항목이 만족도와 양의 상관으로 잡히는가.
사용: python -m scripts.smoke_feedback
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from src.feedback import sample  # noqa: E402
from src.feedback.correlate import build_report, correlations, session_table  # noqa: E402


def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ✓ {msg}")


def _score_rows():
    """8세션 × 18항목. C3_definition 을 세션별로 1→5 변동(만족도 driver)."""
    from src.analyze.checklist import by_key
    keys = list(by_key())
    rows = []
    for i in range(8):
        date = f"2026-03-{i+1:02d}"
        for k in keys:
            # driver 항목은 세션 인덱스 따라 1~5 선형, 나머지는 3 고정(무신호)
            if k in sample.SAT_DRIVERS:
                sc = 1 + round(i * 4 / 7)
            else:
                sc = 3
            rows.append({"date": date, "session": "오전", "item_key": k,
                         "category": k[:2], "score": sc})
    return rows


def test_generate_reproducible():
    print("· 샘플 생성 재현성")
    rows = _score_rows()
    a = sample.generate(rows, seed=42)
    b = sample.generate(rows, seed=42)
    _check(a == b, "같은 seed → 동일 결과(재현성)")
    _check(len({(f["date"], f["session"]) for f in a}) == 8, "8세션 모두 피드백 생성")
    _check(all(1 <= f["satisfaction"] <= 5 for f in a), "만족도 1~5 범위")


def test_driver_correlation():
    print("· driver 항목이 만족도와 양의 상관으로 잡히는가")
    rows = _score_rows()
    fb = sample.generate(rows, seed=42)
    table = session_table(rows, fb)
    corr = correlations(table, "satisfaction")
    top = corr[0]
    _check(top["key"] in sample.SAT_DRIVERS,
           f"최상위 상관 항목이 driver({top['title']}, r={top['pearson']})")
    _check(top["pearson"] > 0.5, f"driver 상관 r>0.5 (got {top['pearson']})")
    # 무신호 항목(고정 3점)은 상관 nan/0 근처
    flat = [d for d in corr if d["key"] not in sample.SAT_DRIVERS
            and d["key"] not in sample.UNDERSTAND_DRIVERS]
    _check(all(np.isnan(d["pearson"]) or abs(d["pearson"]) < 0.5 for d in flat),
           "무신호(고정점수) 항목은 강한 상관 없음")


def test_report():
    print("· build_report")
    rows = _score_rows()
    fb = sample.generate(rows, seed=42)
    md = build_report(rows, fb, instructor="김영아")
    _check("합성 샘플" in md, "합성 데이터 고지 포함")
    _check("만족도와 가장 연관된" in md, "상관 Top 표 존재")
    _check("인사이트" in md, "인사이트 섹션 존재")


def main():
    print("피드백 상관분석 스모크\n")
    test_generate_reproducible()
    test_driver_correlation()
    test_report()
    print("\n✅ 전부 통과 — 생성·상관·리포트 정상(driver 신호 복원 확인).")


if __name__ == "__main__":
    main()
