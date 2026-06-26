"""보고서 저장소 — 여러 강의(보고서)를 reports/<id>/ 폴더로 분리 관리.

한 **보고서(report) = 한 강의(course)**. 그 안에 여러 **세션(txt 분석 결과)**이 쌓인다.
다른 강의(예: 클라우드 컴퓨팅)는 별도 report_id 로 완전히 분리된다.

폴더 구조:
    reports/<report_id>/
        meta.json              보고서 메타(이름·강사·모드·세션목록)
        session_scores.jsonl   전 세션의 분석행(대시보드 입력, 18항목/세션)
        chunks/<date>.jsonl    세션 원문 청크(하이라이트용)

세션 키 = (date, session). session 라벨:
    - mode="ampm"   → 시각 기준 분리 {"오전","오후"}
    - mode="single" → 분리 안 함 {"종일"}
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# core/ 루트 기준 reports/
REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


def _slugify(name: str) -> str:
    """보고서 이름 → 폴더로 안전한 id. 한글은 보존, 경로 위험문자만 제거."""
    s = name.strip().replace("/", "-").replace("\\", "-")
    s = re.sub(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ.\- ]", "", s)
    s = re.sub(r"\s+", "_", s).strip("._-")
    return s or "report"


@dataclass
class Report:
    """보고서 핸들 — meta.json 을 감싸고 경로/입출력을 제공."""

    report_id: str
    dir: Path
    meta: dict

    # ── 경로 ──
    @property
    def scores_path(self) -> Path:
        return self.dir / "session_scores.jsonl"

    @property
    def chunks_dir(self) -> Path:
        return self.dir / "chunks"

    def chunks_path(self, date: str) -> Path:
        return self.chunks_dir / f"{date}.jsonl"

    # ── 메타 접근 ──
    @property
    def name(self) -> str:
        return self.meta.get("name", self.report_id)

    @property
    def mode(self) -> str:
        return self.meta.get("mode", "ampm")  # "ampm" | "single"

    @property
    def sessions(self) -> list[dict]:
        return self.meta.get("sessions", [])

    @property
    def session_labels(self) -> list[str]:
        return ["오전", "오후"] if self.mode == "ampm" else ["종일"]

    def has_session(self, date: str, session: str) -> bool:
        return any(s["date"] == date and s["session"] == session for s in self.sessions)

    # ── 입출력 ──
    def save_meta(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.scores_path.touch(exist_ok=True)
        self.chunks_dir.mkdir(exist_ok=True)
        self.dir.joinpath("meta.json").write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_score_rows(self) -> list[dict]:
        if not self.scores_path.exists():
            return []
        return [json.loads(l) for l in self.scores_path.open(encoding="utf-8") if l.strip()]

    def load_chunks(self) -> dict[tuple[str, str], list[dict]]:
        """(date, session) → [chunk dict]."""
        out: dict[tuple[str, str], list[dict]] = {}
        if not self.chunks_dir.exists():
            return out
        for p in sorted(self.chunks_dir.glob("*.jsonl")):
            for l in p.open(encoding="utf-8"):
                if l.strip():
                    c = json.loads(l)
                    out.setdefault((c["date"], c.get("session")), []).append(c)
        return out

    def add_session(self, *, date: str, session: str, subject: str,
                    source_file: str, rows: list[dict], chunks: list[dict],
                    added_at: str = "") -> None:
        """세션 1개를 보고서에 추가(또는 동일 키 덮어쓰기).

        rows   : 이 세션의 분석행(18항목). date/session/lecture_id 를 강제 정합.
        chunks : 이 세션의 원문 청크.
        """
        lecture_id = f"{date}_{session}"
        # 1) 기존 동일 (date,session) 행 제거 후 새 행 추가
        kept = [r for r in self.load_score_rows()
                if not (r.get("date") == date and r.get("session") == session)]
        for r in rows:
            r["date"], r["session"], r["lecture_id"] = date, session, lecture_id
        with self.scores_path.open("w", encoding="utf-8") as f:
            for r in kept + rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        # 2) chunks 병합(같은 date 파일에 다른 session 이 있을 수 있음)
        self.chunks_dir.mkdir(exist_ok=True)
        cp = self.chunks_path(date)
        other = []
        if cp.exists():
            other = [json.loads(l) for l in cp.open(encoding="utf-8")
                     if l.strip() and json.loads(l).get("session") != session]
        for c in chunks:
            c["date"], c["session"] = date, session
        with cp.open("w", encoding="utf-8") as f:
            for c in other + chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        # 3) meta 갱신(동일 키는 교체)
        self.meta.setdefault("sessions", [])
        self.meta["sessions"] = [s for s in self.meta["sessions"]
                                 if not (s["date"] == date and s["session"] == session)]
        self.meta["sessions"].append(
            {"date": date, "session": session, "subject": subject,
             "source_file": source_file, "added_at": added_at})
        self.meta["sessions"].sort(key=lambda s: (s["date"], s["session"]))
        self.save_meta()


# ── 저장소 레벨 함수 ───────────────────────────────────────────────────
# base = 보고서들이 들어갈 폴더. 멀티테넌트에선 워크스페이스의 reports/ 를 넘긴다.
# 기본값 REPORTS_DIR 은 로컬 단일테넌트(예: kdt-김영아) 하위호환.
def list_reports(base: Path = REPORTS_DIR) -> list[Report]:
    """base 아래 모든 보고서(최근 생성 순)."""
    if not base.exists():
        return []
    out = []
    for d in base.iterdir():
        meta_p = d / "meta.json"
        if d.is_dir() and meta_p.exists():
            out.append(Report(d.name, d, json.loads(meta_p.read_text(encoding="utf-8"))))
    out.sort(key=lambda r: r.meta.get("created_at", ""), reverse=True)
    return out


def load_report(report_id: str, base: Path = REPORTS_DIR) -> Report | None:
    d = base / report_id
    meta_p = d / "meta.json"
    if not meta_p.exists():
        return None
    return Report(report_id, d, json.loads(meta_p.read_text(encoding="utf-8")))


def create_report(name: str, *, instructor: str = "", mode: str = "ampm",
                  created_at: str = "", report_id: str | None = None,
                  base: Path = REPORTS_DIR) -> Report:
    """새 보고서 생성. id 충돌 시 -2, -3 … 으로 회피."""
    slug = report_id or _slugify(name)
    rid, n = slug, 2
    while (base / rid).exists():
        rid, n = f"{slug}-{n}", n + 1
    rpt = Report(rid, base / rid,
                 {"report_id": rid, "name": name, "instructor": instructor,
                  "mode": mode, "created_at": created_at, "sessions": []})
    rpt.save_meta()
    return rpt


def delete_report(report_id: str, base: Path = REPORTS_DIR) -> bool:
    d = base / report_id
    if d.is_dir():
        shutil.rmtree(d)
        return True
    return False


def dir_size(path: Path) -> int:
    """폴더 총 바이트(용량제한 계산용)."""
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
