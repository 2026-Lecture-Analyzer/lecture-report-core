"""검증(P3) — 메타데이터를 '정답(ground-truth)'으로 한 분석 정확도 측정.

담당: P3 (스코어링·검증)
개발할 것: 메타데이터(`강의 메타데이터.csv`)를 정답으로 로드해 우리 결과와 대조.
입력 → 출력: scores.json(우리 결과) + 메타데이터(정답) → 검증 지표 dict
참고: docs/SCHEMA.md, src/preprocess/loader.py(load_metadata)

⚠️ 메타데이터는 정답/검증 전용 — 분석 input(모델 프롬프트)에 절대 넣지 않는다.
"""
from __future__ import annotations

from pathlib import Path


def load_truth(csv_path: Path | None = None):
    """메타데이터를 정답 테이블(pandas DataFrame)로 로드. 분석 input 과 분리."""
    # TODO(P3): loader.load_metadata 로 메타 로드(정답 전용)
    raise NotImplementedError("P3: 구현 필요")


def coverage_check(scores: dict, truth) -> dict:
    """분석된 (date, session) 강의가 메타 정답을 모두 커버하는지."""
    # TODO(P3): scores 의 (date,session) vs 메타의 (date,session) 차집합 비교
    raise NotImplementedError("P3: 구현 필요")


def evaluate(scores: dict, csv_path: Path | None = None) -> dict:
    """검증 묶음."""
    # TODO(P3): 정답으로 쓸 필드 확정 — instructor/time 은 신뢰, subject 는 불일치 주의
    #           (메타 subject ≠ 실제 내용. metadata-content-mismatch 참고)
    # TODO(P3): coverage_check 외 topic_accuracy / instructor_match / 혼동행렬 추가
    # 참고 구현: 파일 하단 주석
    raise NotImplementedError("P3: 구현 필요 — 아래 참고 구현 참조")


# ════════════════════════════════════════════════════════════════════════
# 참고 구현 (Claude 초안 — 지우고 직접 작성하세요)
# ════════════════════════════════════════════════════════════════════════
# import pandas as pd
# from src.preprocess.loader import load_metadata
#
# def load_truth(csv_path=None):
#     return load_metadata(csv_path)
#
# def coverage_check(scores, truth):
#     analyzed = {(v["date"], v["session"]) for v in scores.get("lectures", {}).values()}
#     expected = {(str(d.date()), s) for d, s in zip(truth["date"], truth["session"])}
#     missing = sorted(expected - analyzed)
#     extra = sorted(analyzed - expected)
#     return {"expected": len(expected), "analyzed": len(analyzed),
#             "missing": missing, "extra": extra}
#
# def evaluate(scores, csv_path=None):
#     truth = load_truth(csv_path)
#     return {"coverage": coverage_check(scores, truth)}
