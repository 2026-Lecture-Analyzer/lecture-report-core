"""산출물 재현성 manifest.

팀 협업 + 재현성을 위해, 각 파이프라인 실행마다 다음을 기록한다:
  - 생성 시각, git 커밋, Python/주요 패키지 버전
  - 입력 파일 해시(SHA256) — 데이터가 바뀌면 추적 가능
  - 실행 파라미터(설정 스냅샷), 산출 통계

manifest 자체는 원문을 담지 않으므로 공유 안전(파일명·해시·카운트만).
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

TRACKED_PACKAGES = ["pandas", "numpy", "matplotlib", "konlpy", "jpype1",
                    "transformers", "torch", "accelerate"]


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def _pkg_versions() -> dict[str, str]:
    out = {}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            continue
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_inputs(paths) -> list[dict]:
    return [{"file": Path(p).name, "sha256": file_sha256(p)} for p in sorted(map(Path, paths))]


def write_manifest(out_path: Path, *, step: str, params: dict,
                   stats: dict, inputs=None) -> str:
    """manifest JSON 작성. inputs 는 입력 파일 경로 목록(선택)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "step": step,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": _pkg_versions(),
        "params": params,
        "stats": stats,
        "inputs": hash_inputs(inputs) if inputs else None,
    }
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_path)
