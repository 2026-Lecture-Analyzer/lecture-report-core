"""합성 수강생 피드백 생성 — 실제 세션 점수를 driver 로 삼아 상관 신호를 심는다.

목적: 실데이터가 없어도 (1) 피드백 적재 포맷 (2) 상관분석 메서드 를 end-to-end 로 검증.
설계: 세션마다 일부 강의력 항목(개념설명·예시·실습·구조·속도)을 만족도의 '진짜 동인'으로
두고, 학생별 잡음을 더해 1~5 만족도를 만든다 → 상관분석이 그 동인을 되짚어내는지로 검증.
결정성: seed 고정(config.SEED) → 재현 가능.
"""
from __future__ import annotations

import random

from src import config

# 만족도/이해도의 '진짜 동인' 항목과 가중치(합성 가정 — 리포트에 명시).
SAT_DRIVERS = {
    "C3_definition": 1.0, "C3_analogy": 1.0, "C3_code_explanation": 0.8,
    "C5_example": 0.9, "C5_practice": 0.9, "C2_structure": 0.8, "C4_pace": 0.6,
}
UNDERSTAND_DRIVERS = {
    "C3_definition": 1.0, "C3_term_explanation": 1.0, "C3_prerequisite": 0.9,
    "C3_concept_connection": 0.8, "C2_structure": 0.6,
}

_POS = ["설명이 이해하기 쉬웠어요", "예시 덕분에 개념이 잡혔습니다", "실습 연계가 좋았어요",
        "구조가 명확해서 따라가기 편했습니다"]
_NEG = ["조금 빠르게 느껴졌어요", "선행 개념 설명이 더 있었으면", "용어가 어려웠습니다",
        "반복 표현이 거슬렸어요"]
_MID = ["무난한 강의였어요", "전반적으로 괜찮았습니다"]


def _session_scores(rows: list[dict]) -> dict:
    """session_scores 행 → {(date,session): {item_key: score}}."""
    out: dict = {}
    for r in rows:
        s = r.get("score")
        if isinstance(s, (int, float)):
            out.setdefault((r["date"], r["session"]), {})[r["item_key"]] = s
    return out


def _weighted(scores: dict, drivers: dict) -> float:
    """존재하는 driver 항목만으로 가중 평균(1~5). 없으면 3.0."""
    num = den = 0.0
    for k, w in drivers.items():
        if k in scores:
            num += scores[k] * w
            den += w
    return num / den if den else 3.0


def _clip5(x: float) -> int:
    return max(1, min(5, int(round(x))))


def generate(rows: list[dict], *, students_min: int = 12, students_max: int = 25,
             noise: float = 0.7, seed: int = None) -> list[dict]:
    """세션별 학생 피드백 리스트 생성.

    각 학생: satisfaction/understanding(1~5) = driver 가중평균 + 가우시안 잡음,
    recommend = satisfaction>=4, comment = 만족도 대역별 템플릿.
    """
    rng = random.Random(config.SEED if seed is None else seed)
    sess_scores = _session_scores(rows)
    fb: list[dict] = []
    for (date, session), scores in sorted(sess_scores.items()):
        sat_true = _weighted(scores, SAT_DRIVERS)
        und_true = _weighted(scores, UNDERSTAND_DRIVERS)
        n = rng.randint(students_min, students_max)
        for i in range(n):
            sat = _clip5(sat_true + rng.gauss(0, noise))
            und = _clip5(und_true + rng.gauss(0, noise))
            if sat >= 4:
                comment = rng.choice(_POS)
            elif sat <= 2:
                comment = rng.choice(_NEG)
            else:
                comment = rng.choice(_MID)
            fb.append({
                "date": date, "session": session, "student_id": f"s{i:03d}",
                "satisfaction": sat, "understanding": und,
                "recommend": int(sat >= 4), "comment": comment,
            })
    return fb
