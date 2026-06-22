#!/usr/bin/env bash
# 전체 파이프라인 ①~⑧ 실행 후 Streamlit 대시보드까지 한 방.
#
# 사용법:
#   scripts/run_all.sh                                  # 기본 강의(2026-02-03)
#   scripts/run_all.sh 2026-02-02_kdt-backendj-21th.txt # 다른 강의 파일
#   scripts/run_all.sh 2026-02-03_kdt-backendj-21th.txt --no-dash  # 대시보드 생략
#
# venv(core/.venv)의 python을 직접 호출하므로 activate 불필요.
set -euo pipefail

# 이 스크립트 위치 기준 repo 루트(core) 로 이동 — 어디서 실행해도 동작
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
FILE="${1:-2026-02-03_kdt-backendj-21th.txt}"
DASH=1
[[ "${2:-}" == "--no-dash" || "${1:-}" == "--no-dash" ]] && DASH=0
[[ "${1:-}" == "--no-dash" ]] && FILE="2026-02-03_kdt-backendj-21th.txt"

echo "▶ 강의 파일: $FILE"
echo "▶ ①② 전처리"
"$PY" -m scripts.run_preprocess
echo "▶ ③④⑤ 정제·청킹·태깅 (Upstage, 과금)"
"$PY" -m scripts.run_refine_local --file "$FILE" --fresh
echo "▶ ⑥ 분석 (self-consistency 3, 과금)"
"$PY" -m scripts.run_analyze_local --self-consistency 3
echo "▶ ⑦⑧ 스코어링 + 리포트(MD/PDF)"
"$PY" -m scripts.run_score_local
"$PY" -m scripts.run_report_local --pdf

echo
echo "✅ 산출물: outputs/processed/  (scores.json · reports/report_*.{md,pdf})"

if [[ "$DASH" == "1" ]]; then
  echo "▶ 대시보드 실행 — 브라우저에서 열립니다. 종료는 Ctrl+C"
  exec .venv/bin/streamlit run src/report/dashboard.py
else
  echo "ℹ 대시보드는 생략. 보려면: .venv/bin/streamlit run src/report/dashboard.py"
fi
