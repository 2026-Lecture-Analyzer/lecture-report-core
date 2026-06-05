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
# TODO(P1): SEED_GLOSSARY 확장 — build_candidates 결과를 검수해 corrections/terms 추가
# TODO(P1): rule=True 항목 선별 — 확실한 오류만(과도한 치환은 오작동 위험)
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
SEED_GLOSSARY = {
    "corrections": [
        {"wrong": "잡바", "correct": "Java", "rule": True},
        {"wrong": "잡아이오", "correct": "java.io", "rule": True},
        {"wrong": "브나이어", "correct": "java.nio", "rule": True},
        {"wrong": "NI2", "correct": "NIO2", "rule": True},
        {"wrong": "3레드", "correct": "스레드", "rule": True},
    ],
    "terms": ["Java", "NIO", "스트림", "버퍼", "채널", "셀렉터",
              "테이블", "조인", "인덱스", "트랜잭션", "롤백", "쿼리", "파티션"],
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
        data = extract_json(out)
        if not isinstance(data, dict):   # 모델이 스키마를 안 지킨 경우 스킵
            continue
        for c in data.get("corrections", []) or []:
            # dict {wrong,correct} 또는 [wrong, correct] 둘 다 허용
            if isinstance(c, dict):
                w, r = c.get("wrong"), c.get("correct")
            elif isinstance(c, (list, tuple)) and len(c) >= 2:
                w, r = c[0], c[1]
            else:
                continue
            if isinstance(w, str) and isinstance(r, str) and w and r:
                corr_counter[w] += 1
                corr_map[w] = r
        for t in data.get("terms", []) or []:
            if isinstance(t, str) and t:
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
