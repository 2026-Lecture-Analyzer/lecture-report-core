"""Step 4 — 섹션 정제 (모델 호출, generate_fn 주입).

- 섹션을 순서대로 정제. 직전 섹션 요약을 슬라이딩 윈도우로 다음 섹션에 전달.
- rule=True 용어 치환을 모델 호출 전에 먼저 적용.
- **체크포인트/재개**: clean.jsonl 에 섹션 1건씩 즉시 append. 이미 처리된
  section_id 는 건너뛰고, 마지막 레코드의 summary 로 맥락을 복원한다.
  (Colab 런타임이 끊겨도 이어서 재개 — out_path 를 Google Drive 로 두면 영속)

clean 레코드 스키마:
    {section_id, file, date, session, raw_ref, start_time, end_time,
     clean_text, summary}
"""
from __future__ import annotations

import json
from pathlib import Path

import re

from src import config
from src.refine.glossary import apply_corrections
from src.refine.jsonout import extract_json
from src.refine.prompts import refine_prompt
from src.refine.sectionize import render_section

# render_section 이 붙이는 [CTX] 줄 제거용
_CTX_LINE_RE = re.compile(r"^\[CTX\].*$", re.MULTILINE)


def _load_done(out_path: Path):
    """기존 clean.jsonl 에서 (처리된 section_id 집합, 마지막 summary) 복원."""
    done, last_summary, last_id = set(), "", -1
    p = Path(out_path)
    if not p.exists():
        return done, last_summary
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            done.add(r["section_id"])
            if r["section_id"] > last_id:
                last_id, last_summary = r["section_id"], r.get("summary", "")
    return done, last_summary


def run_refine(sections: list[dict], glossary: dict, generate_fn,
               out_path: Path, log=print, overviews: dict | None = None) -> dict:
    """섹션 정제. overviews={lecture_id: {keywords, outline}} 주면 [강의 개요]를
    전역 맥락으로 프롬프트에 주입한다(§설계철학 A). lecture_id = f"{date}_{session}".
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done, prev_summary = _load_done(out_path)
    if done:
        log(f"[resume] 이미 처리된 섹션 {len(done)}개 건너뜀")

    n_new = 0
    with out_path.open("a", encoding="utf-8") as w:
        for sec in sections:
            if sec["section_id"] in done:
                continue
            overview = None
            if overviews:
                overview = overviews.get(f"{sec['date']}_{sec['session']}")
            rendered = apply_corrections(render_section(sec), glossary)
            out = generate_fn(refine_prompt(rendered, glossary, prev_summary, overview))
            data = extract_json(out) or {}
            clean_text = (data.get("clean_text") or "").strip()
            summary = (data.get("summary") or "").strip()[:config.CONTEXT_SUMMARY_MAX_CHARS]
            if not clean_text:  # 파싱 실패 시 [MAIN] 블록만 추출해 원문 보존(추적성 우선)
                clean_text = _CTX_LINE_RE.sub("", rendered).strip()
                log(f"[warn] section {sec['section_id']} JSON 파싱 실패 — 원문 보존([CTX] 제거)")
            rec = {
                "section_id": sec["section_id"], "file": sec["file"],
                "date": sec["date"], "session": sec["session"],
                "raw_ref": sec["raw_ref"], "start_time": sec["start_time"],
                "end_time": sec["end_time"], "clean_text": clean_text,
                "summary": summary,
            }
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")
            w.flush()  # 체크포인트: 즉시 디스크 반영
            prev_summary = summary or prev_summary
            n_new += 1
            if n_new % 10 == 0:
                log(f"  정제 {n_new}개 완료...")

    return {"sections_total": len(sections), "new": n_new,
            "skipped": len(done), "output": str(out_path)}
