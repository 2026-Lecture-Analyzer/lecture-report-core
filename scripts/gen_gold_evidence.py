"""gold 채점용 증거팩 생성 — 한 강의의 18항목 채점 근거를 자동 추출(검토자용).

순환성 최소화: C1·C5 는 raw(merged) 근거 + 메트릭 제안점수, C2~C4 는 clean 근거(아웃라인·
인용)만 제시하고 점수는 사람이 확정. docs/고도화/gold2_0206_초안 과 같은 양식.

사용법:
    python -m scripts.gen_gold_evidence --date 2026-02-25 --dir outputs/processed/_gold_0225
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.analyze.checklist import CATEGORIES, CHECKLIST  # noqa: E402
from src.analyze.metrics import (_CAS_END, _HON_END, _SENT_SPLIT,  # noqa: E402
                                 compute_metrics, score_global_metric_item,
                                 score_metric_item)


def _find_ctx(txt: str, pats: list[str], n: int, span: int = 32) -> list[str]:
    out = []
    for p in pats:
        for m in re.finditer(re.escape(p), txt):
            i = m.start()
            out.append(txt[max(0, i - span):i + len(p) + 8].replace("\n", " ").strip())
            if len(out) >= n:
                return out
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="gold 증거팩 생성")
    ap.add_argument("--date", required=True)
    ap.add_argument("--dir", type=Path, required=True, help="clean.jsonl 폴더(_gold_XXXX)")
    ap.add_argument("--merged", type=Path, default=config.PROCESSED_DIR / "merged.jsonl")
    ap.add_argument("--raw", type=Path, default=config.PROCESSED_DIR / "raw.jsonl")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    d = args.date

    merged = [json.loads(l) for l in args.merged.open(encoding="utf-8") if l.strip()]
    mb = [b for b in merged if b["date"] == d]
    raw = [json.loads(l) for l in args.raw.open(encoding="utf-8") if l.strip()]
    rt = [u.get("text", "") for u in raw if u["date"] == d]
    clean = [json.loads(l) for l in (args.dir / "clean.jsonl").open(encoding="utf-8") if l.strip()]
    if not mb or not clean:
        sys.exit(f"{d} 데이터 없음(merged {len(mb)} / clean {len(clean)})")

    m = compute_metrics(mb, raw_texts=rt)
    raw_txt = " ".join(b["text"] for b in mb)
    clean_txt = " ".join(c["clean_text"] for c in clean)

    # 메트릭 제안점수(C1·C5·pace)
    def msc(k):
        r = score_metric_item(k, m)
        if r["score"] is None:
            r = score_global_metric_item(k, m)
        return r["score"] if r else "?"

    # 상위 필러 / 반말 예시 / cue 예시
    words = re.findall(r"[가-힣A-Za-z0-9]+", raw_txt)
    fcnt = Counter(w for w in words if w in set(config.FILLER_WORDS))
    cas = [s.strip() for s in _SENT_SPLIT.split(raw_txt)
           if s.strip() and not _HON_END.search(s.strip()) and _CAS_END.search(s.strip())]
    check_ex = _find_ctx(raw_txt, config.C5_CHECK_CUES, 5)
    engage_ex = _find_ctx(raw_txt, config.C5_ENGAGE_CUES, 5)

    # clean 아웃라인 / 도입 / 종료
    byses = defaultdict(list)
    for c in clean:
        byses[c["session"]].append(c)
    outline = []
    for s in ("오전", "오후"):
        for c in sorted(byses.get(s, []), key=lambda x: x["section_id"]):
            sm = (c.get("summary") or "")[:62]
            if sm:
                outline.append(f"  [{c['start_time'][:5]}] {sm}")
    intro = (sorted(byses.get("오전", clean), key=lambda x: x["section_id"])[0]["clean_text"][:400]
             if byses.get("오전") or clean else "")
    last_sec = sorted(byses.get("오후", clean), key=lambda x: x["section_id"])[-1]
    outro = last_sec["clean_text"][-350:]
    analogy = _find_ctx(clean_txt, ["처럼", "마치 ", "비유", "쉽게 말"], 4)
    error = _find_ctx(clean_txt, ["에러", "오류", "안 되", "안돼", "예외"], 4)

    L = []
    L.append(f"# Gold 증거팩 ({d}) — 검토용\n")
    L.append(f"- 상태 🔶 초안(검토자 점수 확정 필요) · 메트릭 {m['n_blocks']}블록 / clean {len(clean)}섹션\n")
    L.append("## C1 언어 표현 (raw 근거 + 메트릭 제안)")
    L.append(f"- 필러율 **{m['filler_rate']}** ({m['filler_n']}회), 지배 필러 '{m['top_filler']}' "
             f"{m['max_filler_rate']} · 상위 {fcnt.most_common(6)}")
    L.append(f"- 존댓말비율 **{m['honorific_ratio']}** · 발화 미완결 {m['incomplete_ratio_utt']}")
    L.append(f"- 반말 종결 예: " + " / ".join(f'"…{s[-32:]}"' for s in cas[:4]))
    L.append(f"- 제안: C1_repetition **{msc('C1_repetition')}** · C1_consistency "
             f"**{msc('C1_consistency')}** · C1_completeness **{msc('C1_completeness')}**\n")
    L.append("## C5 상호작용 (raw 근거 + 메트릭 제안)")
    L.append(f"- 이해확인 {m['check_cue_n']}회({m['check_per10']}/10분) 예: {check_ex[:4]}")
    L.append(f"- 참여유도 {m['engage_cue_n']}회({m['engage_per10']}/10분) 예: {engage_ex[:4]}")
    L.append(f"- 제안: C5_check **{msc('C5_check')}** · C5_engage **{msc('C5_engage')}** · "
             f"C5_answer ?(단일화자, 보통 1~2)\n")
    L.append("## C2 도입/구조 · C3 개념 · C4 실습 (clean 근거 — 점수는 사람이)")
    L.append("**아웃라인(섹션 요약):**")
    L.extend(outline[:18])
    L.append(f"\n**도입부(목표/복습 확인):** {intro}\n")
    L.append(f"**종료부(요약 확인):** …{outro}\n")
    L.append(f"**비유/예시:** " + " / ".join(f'"{s}"' for s in analogy[:3]))
    L.append(f"**오류대응:** " + " / ".join(f'"{s}"' for s in error[:3]) + "\n")
    L.append("## 채점표 (← 확정 점수 기입)\n")
    L.append("| 항목 | 카테고리 | 제안(메트릭) | 확정 |")
    L.append("|---|---|---|---|")
    metric_keys = {"C1_repetition", "C1_consistency", "C1_completeness",
                   "C3_pace", "C5_check", "C5_engage"}
    for it in CHECKLIST:
        sug = msc(it["key"]) if it["key"] in metric_keys else "(읽고 판단)"
        L.append(f"| {it['key']} | {CATEGORIES[it['category']]} > {it['title']} | {sug} | |")

    out = args.out or args.dir.parent.parent.parent / "docs" / "고도화" / f"gold_evidence_{d}.md"
    out = Path("docs/고도화") / f"gold_evidence_{d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"[증거팩] {d} → {out}  (필러 {m['filler_rate']}·존댓말 {m['honorific_ratio']}·"
          f"check {m['check_per10']}/10분)")


if __name__ == "__main__":
    main()
