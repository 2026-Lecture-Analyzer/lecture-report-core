"""Step 0~2 전처리 실행 (규칙 기반, GPU 불필요 — 로컬에서 실행).

raw.jsonl → speaker_map.json → merged.jsonl + manifest.json 생성.
이후 Step 3~5(용어집·정제·청킹)는 Colab 노트북(notebooks/02_refine_colab.ipynb)에서
merged.jsonl 을 입력으로 실행한다.

사용법:
    python -m scripts.run_preprocess
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.manifest import write_manifest  # noqa: E402
from src.preprocess.merge import run_step2  # noqa: E402
from src.preprocess.parse import write_raw_jsonl  # noqa: E402


def main() -> None:
    out_dir = config.PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[Step 1] 파싱 → raw.jsonl")
    raw_path = out_dir / "raw.jsonl"
    s1 = write_raw_jsonl(raw_path)
    print(f"  발화 {s1['records']:,}건 / 파일 {s1['files']}개 / malformed {s1['malformed']}")

    print("[Step 2] 화자 매핑 + 발화 병합 → merged.jsonl")
    s2 = run_step2(raw_path, out_dir)
    print(f"  블록 {s2['blocks']:,}개 (입력 {s2['input_records']:,} 발화)")

    inputs = sorted(Path(config.SCRIPT_DIR).glob("*.txt"))
    mpath = write_manifest(
        out_dir / "manifest_preprocess.json",
        step="preprocess(step0-2)",
        params={
            "merge_gap_sec": config.MERGE_GAP_SEC,
            "merge_max_block_sec": config.MERGE_MAX_BLOCK_SEC,
            "merge_max_block_chars": config.MERGE_MAX_BLOCK_CHARS,
        },
        stats={"step1": s1, "step2": s2},
        inputs=inputs,
    )
    print(f"[manifest] {mpath}")
    print("완료. 다음 단계: Colab에서 merged.jsonl 로 용어집·정제·청킹 실행.")


if __name__ == "__main__":
    main()
