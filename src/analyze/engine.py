"""분석 엔진(P2) — chunks.jsonl → analysis.jsonl.

담당: P2 (분석 엔진)
개발할 것: 강의(파일·세션) 단위로 18개 체크리스트 항목을 LLM으로 평가하는 실행 루프.
           refine 과 동일하게 generate_fn 주입(모델 분리) + 체크포인트/재개.
입력 → 출력: chunks.jsonl + generate_fn → analysis.jsonl (항목 1건 = 1행)
참고: docs/SCHEMA.md(analysis.jsonl), src/refine/refine.py(체크포인트 패턴),
      src/analyze/prompts.py(item_prompt), src/analyze/checklist.py(CHECKLIST)
"""
from __future__ import annotations

from pathlib import Path


def load_chunks(path: Path) -> list[dict]:
    """chunks.jsonl 로드."""
    # TODO(P2): chunks.jsonl 한 줄씩 json.loads 해서 리스트로 반환
    raise NotImplementedError("P2: 구현 필요")


def group_by_lecture(chunks: list[dict]) -> dict[str, list[dict]]:
    """강의 단위 = (date, session). lecture_id = '{date}_{session}'."""
    # TODO(P2): chunks 를 '{date}_{session}' 키로 묶어 dict 반환
    raise NotImplementedError("P2: 구현 필요")


def run_analysis(chunks_path: Path, generate_fn, out_path: Path, log=print) -> dict:
    """강의×18항목 평가 → analysis.jsonl. 체크포인트/재개 지원.

    반환 예: {"lectures": N, "new_rows": M, "skipped": K, "output": path}
    """
    # TODO(P2): 강의×18항목(CHECKLIST) 평가 → item_prompt → generate_fn → extract_json
    # TODO(P2): 결과를 analysis.jsonl 에 1행씩 append + flush (체크포인트)
    # TODO(P2): 재개 — 이미 평가된 (lecture_id, item_key) 쌍은 건너뛰기
    # TODO(P2): 토큰 초과 대비 — 항목별 관련 청크만 선별(임베딩 검색) [고도화]
    # TODO(P2): (선택) self-consistency(다회 샘플 다수결)로 점수 신뢰도↑
    # 참고 구현: 파일 하단 주석
    raise NotImplementedError("P2: 구현 필요 — 아래 참고 구현 참조")


# ════════════════════════════════════════════════════════════════════════
# 참고 구현 (Claude 초안 — 지우고 직접 작성하세요)
# ════════════════════════════════════════════════════════════════════════
# import json
# from collections import defaultdict
# from src.analyze.checklist import CHECKLIST
# from src.analyze.prompts import item_prompt
# from src.refine.jsonout import extract_json
#
# def load_chunks(path):
#     with Path(path).open(encoding="utf-8") as f:
#         return [json.loads(line) for line in f if line.strip()]
#
# def group_by_lecture(chunks):
#     groups = defaultdict(list)
#     for c in chunks:
#         groups[f"{c['date']}_{c['session']}"].append(c)
#     return groups
#
# def _done_keys(out_path):
#     p = Path(out_path)
#     if not p.exists():
#         return set()
#     done = set()
#     with p.open(encoding="utf-8") as f:
#         for line in f:
#             if line.strip():
#                 r = json.loads(line)
#                 done.add((r["lecture_id"], r["item_key"]))
#     return done
#
# def run_analysis(chunks_path, generate_fn, out_path, log=print):
#     out_path = Path(out_path)
#     out_path.parent.mkdir(parents=True, exist_ok=True)
#     lectures = group_by_lecture(load_chunks(chunks_path))
#     done = _done_keys(out_path)
#     if done:
#         log(f"[resume] 이미 평가된 (강의,항목) {len(done)}쌍 건너뜀")
#     n_new = 0
#     with out_path.open("a", encoding="utf-8") as w:
#         for lecture_id, lec_chunks in lectures.items():
#             meta = lec_chunks[0]
#             for item in CHECKLIST:
#                 if (lecture_id, item["key"]) in done:
#                     continue
#                 out = generate_fn(item_prompt(item, lec_chunks))
#                 data = extract_json(out) or {}
#                 rec = {
#                     "lecture_id": lecture_id, "file": meta["file"],
#                     "date": meta["date"], "session": meta["session"],
#                     "item_key": item["key"], "category": item["category"],
#                     "score": data.get("score"), "verdict": data.get("verdict"),
#                     "evidence": data.get("evidence", []),
#                     "comment": (data.get("comment") or "").strip(),
#                 }
#                 w.write(json.dumps(rec, ensure_ascii=False) + "\n")
#                 w.flush()
#                 n_new += 1
#             log(f"  강의 {lecture_id} 18항목 평가 완료")
#     return {"lectures": len(lectures), "new_rows": n_new,
#             "skipped": len(done), "output": str(out_path)}
