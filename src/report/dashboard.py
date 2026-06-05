"""대시보드(P4) — Streamlit.

담당: P4 (리포트·대시보드·인프라)
개발할 것: scores.json / analysis.jsonl 을 시각화하는 Streamlit 대시보드.
실행: streamlit run src/report/dashboard.py
참고: docs/SCHEMA.md(scores.json), streamlit 은 별도 설치(requirements 미포함)
"""
from __future__ import annotations


def main() -> None:
    """Streamlit 앱 진입점."""
    # TODO(P4): 강의 선택 → 종합점수 + 카테고리(레이더/바) 차트
    # TODO(P4): 항목별 평가·근거 인용 드릴다운
    # TODO(P4): 강사별·주차별 비교 뷰
    # TODO(P4): 리포트 PDF 다운로드 버튼
    # 참고 구현: 파일 하단 주석
    raise NotImplementedError("P4: 구현 필요 — 아래 참고 구현 참조")


# ════════════════════════════════════════════════════════════════════════
# 참고 구현 (Claude 초안 — 지우고 직접 작성하세요)
# ════════════════════════════════════════════════════════════════════════
# import json
# from pathlib import Path
# from src import config
#
# def main():
#     import streamlit as st
#     st.set_page_config(page_title="강의력 분석 대시보드", layout="wide")
#     st.title("🎓 강의력 분석 대시보드")
#     scores_path = config.PROCESSED_DIR / "scores.json"
#     if not scores_path.exists():
#         st.warning("scores.json 이 없습니다. 스코어링(P3)을 먼저 실행하세요.")
#         return
#     scores = json.loads(Path(scores_path).read_text(encoding="utf-8"))
#     lectures = scores.get("lectures", {})
#     lid = st.selectbox("강의 선택", sorted(lectures))
#     lec = lectures[lid]
#     st.metric("종합 강의력 점수", f"{lec['total_score']} / 100")
#     st.bar_chart(lec["category_scores"])


if __name__ == "__main__":
    main()
