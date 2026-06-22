"""[벤치] Upstage vs Google 전체 파이프라인 비교 — 강의×백엔드로 refine+하이브리드 풀런.

각 (백엔드, 강의)마다: refine(백엔드별 정제·임베딩) → 하이브리드 채점(백엔드별 holistic).
산출: outputs/processed/_bench/{backend}/{date}/{clean,chunks,hybrid_analysis}.jsonl
재개 가능 — hybrid_analysis.jsonl 이 이미 있으면 건너뜀. 진행 로그 출력.

전처리(merged/raw)는 규칙 기반이라 공유(outputs/processed/). 리포트는 scripts/bench_report.py.

사용법:
    python -m scripts.run_backend_bench                    # 전 강의×(upstage,google)
    python -m scripts.run_backend_bench --backends google  # 한 백엔드만
    python -m scripts.run_backend_bench --max 5            # 앞 5강의만(테스트)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python")
SCRIPT_DIR = ROOT / "AI_Lecture_Analysis_Report_Generator" / "강의 스크립트"
MERGED = "outputs/processed/merged.jsonl"


def _run(cmd: list[str], backend: str) -> tuple[bool, float]:
    env = {**os.environ, "LLM_BACKEND": backend}
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    dt = time.time() - t0
    if r.returncode != 0:
        print(f"    ⚠ 실패({dt:.0f}s): {' '.join(cmd[-3:])}\n    {r.stderr.strip()[-300:]}")
        return False, dt
    return True, dt


def main() -> None:
    ap = argparse.ArgumentParser(description="[벤치] 백엔드별 전체 파이프라인")
    ap.add_argument("--backends", nargs="+", default=["upstage", "google"])
    ap.add_argument("--sc", type=int, default=3)
    ap.add_argument("--max", type=int, default=None, help="앞 N강의만")
    args = ap.parse_args()

    files = sorted(p.name for p in SCRIPT_DIR.glob("*.txt"))
    if args.max:
        files = files[: args.max]
    print(f"[벤치] 강의 {len(files)} × 백엔드 {args.backends} · SC {args.sc}")

    t_start = time.time()
    for bk in args.backends:
        for i, f in enumerate(files, 1):
            date = f.split("_")[0]
            d = Path(f"outputs/processed/_bench/{bk}/{date}")
            tag = f"[{bk} {i}/{len(files)} {date}]"
            if (d / "hybrid_analysis.jsonl").exists():
                print(f"{tag} 건너뜀(완료)")
                continue
            print(f"{tag} refine…", flush=True)
            ok, dt1 = _run([PY, "-m", "scripts.run_refine_local", "--file", f,
                            "--out-dir", str(d), "--fresh"], bk)
            if not ok:
                continue
            print(f"{tag} 하이브리드 채점… (refine {dt1:.0f}s)", flush=True)
            ok, dt2 = _run([PY, "-m", "scripts.run_hybrid_eval", "--dir", str(d),
                            "--merged", MERGED, "--by-date", "--self-consistency",
                            str(args.sc)], bk)
            print(f"{tag} ✓ ({dt1:.0f}+{dt2:.0f}s)")
    print(f"[벤치] 전체 완료 — {(time.time()-t_start)/60:.0f}분. 리포트: "
          f"python -m scripts.bench_report")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
