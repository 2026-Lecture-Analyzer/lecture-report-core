"""코칭 리포트 배관 스모크 — LLM 없이 집계·우선순위·조립을 검증.

사용: python -m scripts.smoke_coaching
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.coaching import (aggregate, build_coaching_report,  # noqa: E402
                                 pick_priorities, pick_strengths)


def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ✓ {msg}")


def _rows():
    """가짜 분석행 2세션 — C5_practice 는 항상 1점(약점), C3_definition 항상 5점(강점)."""
    items = [
        ("C1_repetition", "C1", [2, 2]),
        ("C3_definition", "C3", [5, 5]),          # 강점(high)
        ("C5_practice", "C5", [1, 1]),            # 약점(high) — 우선순위 1위 기대
        ("C2_summary", "C2", [2, 3]),             # low weight
    ]
    rows = []
    for di, (date, sess) in enumerate([("2026-02-02", "오전"), ("2026-02-03", "오전")]):
        for key, cat, scs in items:
            rows.append({
                "lecture_id": f"{date}_{sess}", "date": date, "session": sess,
                "item_key": key, "category": cat, "score": scs[di],
                "evidence": [{"chunk_id": "c1", "quote": f"{key} 근거 발화 {di}"}],
                "comment": f"{key} 코멘트", "verdict": "",
            })
    return rows


def test_aggregate():
    print("· aggregate")
    agg = aggregate(_rows())
    _check(len(agg) == 4, f"4항목 집계 (got {len(agg)})")
    _check(agg["C5_practice"]["mean"] == 1.0, "C5_practice 평균 1.0")
    _check(agg["C3_definition"]["mean"] == 5.0, "C3_definition 평균 5.0")
    _check(agg["C5_practice"]["weight_v"] == 3, "C5_practice 가중치 high=3")


def test_priorities():
    print("· pick_priorities / strengths")
    agg = aggregate(_rows())
    pri = pick_priorities(agg, 3)
    _check(pri[0]["key"] == "C5_practice",
           f"우선순위 1위=C5_practice(가중결손 최대) (got {pri[0]['key']})")
    # deficit: C5=3*(5-1)=12, C1=3*(5-2)=9, C2=1*(5-2.5)=2.5
    _check(abs(pri[0]["deficit"] - 12.0) < 1e-6, f"deficit=12 (got {pri[0]['deficit']})")
    st = pick_strengths(agg, 1)
    _check(st[0]["key"] == "C3_definition", "강점 1위=C3_definition")


def test_report_no_llm():
    print("· build_coaching_report (LLM 없음)")
    md = build_coaching_report(_rows(), instructor="김영아", period="2026-02", generate_fn=None)
    _check("김영아 강의 코칭 리포트" in md, "헤더에 강사명")
    _check("개선 우선순위" in md and "실습 연계" in md, "우선순위에 실습 연계(C5_practice)")
    _check("강점" in md and "개념 정의" in md, "강점에 개념 정의(C3_definition)")
    _check("실제 강의 근거" in md, "근거 인용 섹션 존재")


def test_report_with_stub_llm():
    print("· build_coaching_report (stub LLM)")
    def stub(messages):
        return json.dumps({"diagnosis": "근거상 실습 연계가 약함",
                           "how_to": "이론 직후 5분 실습을 배치",
                           "example_lines": ["자, 방금 배운 걸 직접 해봅시다"]},
                          ensure_ascii=False)
    md = build_coaching_report(_rows(), instructor="김영아", generate_fn=stub, log=lambda *a: None)
    _check("진단" in md and "실습 연계가 약함" in md, "LLM 진단 반영")
    _check("바로 쓸 수 있는 멘트" in md, "예시 멘트 반영")
    _check("직접 해봅시다" in md, "예시 멘트 내용 포함")


def main():
    print("코칭 리포트 스모크 — LLM 없이 집계·우선순위·조립 검증\n")
    test_aggregate()
    test_priorities()
    test_report_no_llm()
    test_report_with_stub_llm()
    print("\n✅ 전부 통과 — 집계·우선순위·코칭 조립 정상.")


if __name__ == "__main__":
    main()
