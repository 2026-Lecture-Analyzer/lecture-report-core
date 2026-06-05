"""EDA 리포트 생성 실행 스크립트.

사용법:
    python -m scripts.run_eda
또는
    python scripts/run_eda.py

결과: outputs/eda/eda_report.md + outputs/eda/figures/*.png
"""
import sys
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가 (스크립트 직접 실행 대비)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eda.report import build_report  # noqa: E402


def main() -> None:
    print("EDA 리포트 생성 중... (KoNLPy JVM 기동에 수 초 소요)")
    out = build_report()
    print(f"완료 → {out}")


if __name__ == "__main__":
    main()
