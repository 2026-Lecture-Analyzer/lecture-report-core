"""Step 3 — 도메인 용어집.
두 갈래로 운용한다(보강 사항):
  - corrections: STT 오류 → 표준 표기. `rule=True`인 항목은 모델 정제 전에
    **규칙(문자열 치환)으로 먼저 적용**해 일관성을 높이고 모델 부담을 줄인다.
  - terms: 핵심 도메인 용어 목록(분석/청킹 시 참고).
`build_candidates()`가 모델로 후보를 모아 glossary_candidates.json 을 만들면,
사람이 검수해 glossary.json(확정본)으로 옮긴다. SEED_GLOSSARY 는 EDA에서 확인된
명백한 오류로 시작점을 제공한다.
담당: P1 (정제 고도화) — 이 파일은 동작하는 베이스라인. 아래 TODO가 P1 과제.
"""
# TODO(P1): build_candidates 의 sample_every 조정으로 비용/커버리지 균형
# TODO(P1): 확정본 glossary.json 을 Drive/repo에 버전 관리(팀 공유)
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from src.refine.jsonout import extract_json
from src.refine.prompts import glossary_prompt
from src.refine.sectionize import render_section

# EDA에서 확인된 명백한 STT 오류 시드 (rule=True → 모델 전에 치환)
# 실측 근거: 6개 파일 약 8,600 발화 분석 결과 (2026-02-02 ~ 02-12)
# rule=True  — 문맥 무관하게 치환 가능한 확실한 오류
# rule=False — 동음이의어 가능성 있음 → 모델이 문맥으로 처리
SEED_GLOSSARY = {
    "corrections": [
        # ── 기존 시드 (원본 유지) ──────────────────────────
        {"wrong": "잡바",         "correct": "Java",      "rule": True},
        {"wrong": "잡아이오",     "correct": "java.io",   "rule": True},
        {"wrong": "브나이어",     "correct": "java.nio",  "rule": True},
        {"wrong": "NI2",          "correct": "NIO2",      "rule": True},
        {"wrong": "3레드",        "correct": "스레드",    "rule": True},

        # ── EDA 확장 시드 — SQL/DB 키워드 ─────────────────
        {"wrong": "조인",         "correct": "JOIN",      "rule": True},  # 651회
        {"wrong": "셀렉",         "correct": "SELECT",    "rule": True},  # 366회
        {"wrong": "크리에이트",   "correct": "CREATE",    "rule": True},  # 54회
        {"wrong": "딜리트",       "correct": "DELETE",    "rule": True},  # 47회
        {"wrong": "인서트",       "correct": "INSERT",    "rule": True},  # 34회
        {"wrong": "유니온",       "correct": "UNION",     "rule": True},  # 64회
        {"wrong": "서브쿼리",     "correct": "subquery",  "rule": True},  # 75회
        {"wrong": "서브컬",       "correct": "subquery",  "rule": True},  # 39회
        {"wrong": "서브퀄",       "correct": "subquery",  "rule": True},  # 16회
        {"wrong": "에스큐엘",     "correct": "SQL",       "rule": True},  # 11회

        # ── EDA 확장 시드 — MySQL ──────────────────────────
        {"wrong": "마이에큐엘",   "correct": "MySQL",     "rule": True},  # 3회
        {"wrong": "마이에스큐엘", "correct": "MySQL",     "rule": True},  # 11회
        {"wrong": "마이에큐L",    "correct": "MySQL",     "rule": True},  # 12회

        # ── EDA 확장 시드 — Java / OOP ────────────────────
        {"wrong": "자바",         "correct": "Java",      "rule": True},  # 129회
        {"wrong": "클래스",       "correct": "class",     "rule": True},  # 136회
        {"wrong": "오브젝트",     "correct": "object",    "rule": True},  # 75회
        {"wrong": "인터페이스",   "correct": "interface", "rule": True},  # 60회
        {"wrong": "펑션",         "correct": "function",  "rule": True},  # 66회

        # ── EDA 확장 시드 — Java 타입 ─────────────────────
        {"wrong": "스트링",       "correct": "String",    "rule": True},  # 89회
        {"wrong": "인티저",       "correct": "Integer",   "rule": True},  # 5회
        {"wrong": "부울",         "correct": "Boolean",   "rule": True},
        {"wrong": "어레이",       "correct": "array",     "rule": True},  # 5회

        # ── EDA 확장 시드 — 기타 기술 ─────────────────────
        {"wrong": "파이썬",       "correct": "Python",     "rule": True},  # 7회
        {"wrong": "제이에스",     "correct": "JavaScript", "rule": True},

        # ── rule=False — 동음이의어 주의, 모델 처리 ────────
        {"wrong": "리스트", "correct": "List", "rule": False},  # 35회, '목록' 혼용
        {"wrong": "맵",     "correct": "Map",  "rule": False},  # 20회, '지도' 혼용
    ],
    "terms": [
        # 기존
        "Java", "NIO", "스트림", "버퍼", "채널", "셀렉터",
        "테이블", "조인", "인덱스", "트랜잭션", "롤백", "쿼리", "파티션",
        # EDA 확장
        "MySQL", "SQL", "SELECT", "INSERT", "DELETE", "CREATE", "UNION",
        "subquery", "JOIN", "function", "class", "object", "interface",
        "String", "Integer", "Boolean", "List", "Map", "array",
        "Python", "JavaScript",
    ],
}


def load_glossary(path: Path | None) -> dict:
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(SEED_GLOSSARY)


def apply_corrections(text: str, glossary: dict) -> str:
    """rule=True 인 correction 만 결정적 문자열 치환."""
    for c in glossary.get("corrections", []):
        if c.get("rule") and c.get("wrong"):
            text = text.replace(c["wrong"], c["correct"])
    return text


def build_candidates(sections: list[dict], generate_fn, out_path: Path,
                     sample_every: int = 1) -> dict:
    """섹션을 훑어 용어집 후보를 집계하고 candidates JSON 저장(사람 검수용)."""
    corr_counter: Counter = Counter()
    corr_map: dict[str, str] = {}
    term_counter: Counter = Counter()

    for i, sec in enumerate(sections):
        if i % sample_every:
            continue
        out = generate_fn(glossary_prompt(render_section(sec)))
        data = extract_json(out) or {}
        for c in data.get("corrections", []):
            w, r = c.get("wrong"), c.get("correct")
            if w and r:
                corr_counter[w] += 1
                corr_map[w] = r
        for t in data.get("terms", []):
            if t:
                term_counter[t] += 1

    candidates = {
        "corrections": [{"wrong": w, "correct": corr_map[w], "count": n, "rule": False}
                        for w, n in corr_counter.most_common()],
        "terms": [{"term": t, "count": n} for t, n in term_counter.most_common()],
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(candidates, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    return candidates
