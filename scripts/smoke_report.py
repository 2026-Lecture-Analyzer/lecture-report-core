"""⑧ 리포트 스모크 — scores+analysis → MD 생성·필수 섹션 검증.

사용법: python -m scripts.smoke_report
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.build import build_all, build_lecture_report  # noqa: E402
from src.scoring.scoring import compute_scores  # noqa: E402


def main():
    rows = [
        {"lecture_id": "2026-02-02_오전", "date": "2026-02-02", "session": "오전",
         "item_key": "C2_objective", "category": "C2", "score": 4, "verdict": "양호",
         "evidence": [{"chunk_id": 3, "quote": "오늘 배울 목표는 입출력입니다"}],
         "metric": None, "comment": "학습 목표를 명확히 안내", "routing": {}},
        {"lecture_id": "2026-02-02_오전", "date": "2026-02-02", "session": "오전",
         "item_key": "C1_repetition", "category": "C1", "score": 5, "verdict": "",
         "evidence": [], "metric": {"name": "filler_rate", "value": 0.04},
         "comment": "필러 적음", "routing": {}},
        {"lecture_id": "2026-02-02_오전", "date": "2026-02-02", "session": "오전",
         "item_key": "C5_check", "category": "C5", "score": 1, "verdict": "없음",
         "evidence": [], "metric": None, "comment": "이해 확인 질문 없음",
         "routing": {"negative_evidence": True}},
    ]
    scores = compute_scores(rows)
    tmp = Path(tempfile.mkdtemp())
    ap = tmp / "analysis.jsonl"
    ap.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    sp = tmp / "scores.json"
    sp.write_text(json.dumps(scores, ensure_ascii=False), encoding="utf-8")

    md = build_lecture_report("2026-02-02_오전", scores, rows)
    for must in ["종합 강의력 점수", "카테고리별 점수", "강점", "개선점", "항목별 상세",
                 "학습 목표 안내", "오늘 배울 목표는 입출력입니다", "filler_rate"]:
        assert must in md, f"리포트에 '{must}' 누락"

    r = build_all(sp, ap, tmp / "reports")
    assert r["reports"] == 1, "리포트 수 오류"
    assert Path(r["files"][0]).exists(), "리포트 파일 미생성"

    print(f"리포트 길이 {len(md)}자, 섹션·근거인용·지표 포함")
    print("\n✅ 통과 — 리포트 생성·필수 섹션·근거 인용·지표 표기 정상")


if __name__ == "__main__":
    main()
