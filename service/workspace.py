"""워크스페이스 — 멀티테넌트 단위. 구글 사용자가 만들고, 초대링크로 합류.

저장 루트: env LECTURE_DATA_DIR (기본 core/workspaces/). 각 워크스페이스:
    workspaces/<wid>/
        workspace.json     id·이름·소유자·멤버·초대토큰·용량제한
        reports/<rid>/     보고서들(store.Report) — 워크스페이스 격리

※ 비공개 김영아 데이터(core/reports/)와 물리적으로 분리 → 배포 시 workspaces/ 만 올림.

용량제한: env LECTURE_QUOTA_MB (기본 200MB) — 워크스페이스별 디스크 사용 상한.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from service.store import _slugify, dir_size

CORE = Path(__file__).resolve().parents[1]
DEFAULT_QUOTA_MB = int(os.environ.get("LECTURE_QUOTA_MB", "200"))


def ws_root() -> Path:
    root = Path(os.environ.get("LECTURE_DATA_DIR", CORE / "workspaces"))
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class Workspace:
    wid: str
    dir: Path
    data: dict

    @property
    def name(self) -> str:
        return self.data.get("name", self.wid)

    @property
    def owner(self) -> str:
        return self.data.get("owner_uid", "")

    @property
    def members(self) -> dict:
        return self.data.setdefault("members", {})

    @property
    def reports_dir(self) -> Path:
        d = self.dir / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def quota_bytes(self) -> int:
        return self.data.get("quota_bytes", DEFAULT_QUOTA_MB * 1024 * 1024)

    def is_member(self, uid: str) -> bool:
        return uid in self.members

    def role(self, uid: str) -> str:
        return self.members.get(uid, {}).get("role", "")

    def usage_bytes(self) -> int:
        return dir_size(self.dir)

    def quota_remaining(self) -> int:
        return max(0, self.quota_bytes - self.usage_bytes())

    def over_quota(self, extra: int = 0) -> bool:
        return self.usage_bytes() + extra > self.quota_bytes

    # ── 변경 ──
    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "workspace.json").write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_member(self, user: dict, role: str = "member") -> None:
        self.members[user["uid"]] = {"email": user.get("email", ""), "role": role,
                                     "joined_at": user.get("_now", "")}
        self.save()

    def create_invite(self, by_uid: str, *, now: str = "") -> str:
        token = secrets.token_urlsafe(12)
        self.data.setdefault("invites", []).append(
            {"token": token, "created_by": by_uid, "created_at": now})
        self.save()
        return token

    def revoke_invite(self, token: str) -> None:
        self.data["invites"] = [i for i in self.data.get("invites", []) if i["token"] != token]
        self.save()


# ── 저장소 레벨 ────────────────────────────────────────────────────────
def load_workspace(wid: str) -> Workspace | None:
    p = ws_root() / wid / "workspace.json"
    if not p.exists():
        return None
    return Workspace(wid, ws_root() / wid, json.loads(p.read_text(encoding="utf-8")))


def list_workspaces_for(uid: str) -> list[Workspace]:
    out = []
    for d in ws_root().iterdir():
        if d.is_dir() and (d / "workspace.json").exists():
            ws = load_workspace(d.name)
            if ws and ws.is_member(uid):
                out.append(ws)
    out.sort(key=lambda w: w.data.get("created_at", ""), reverse=True)
    return out


def create_workspace(name: str, owner: dict, *, now: str = "",
                     quota_mb: int | None = None) -> Workspace:
    slug = _slugify(name) or "workspace"
    wid, n = slug, 2
    while (ws_root() / wid).exists():
        wid, n = f"{slug}-{n}", n + 1
    ws = Workspace(wid, ws_root() / wid, {
        "wid": wid, "name": name, "owner_uid": owner["uid"],
        "created_at": now, "invites": [],
        "quota_bytes": (quota_mb or DEFAULT_QUOTA_MB) * 1024 * 1024,
        "members": {owner["uid"]: {"email": owner.get("email", ""),
                                   "role": "owner", "joined_at": now}}})
    ws.save()
    return ws


def accept_invite(token: str, user: dict, *, now: str = "") -> Workspace | None:
    """초대 토큰으로 합류. 성공 시 워크스페이스 반환(이미 멤버면 그대로)."""
    if not token:
        return None
    for d in ws_root().iterdir():
        ws = load_workspace(d.name) if (d / "workspace.json").exists() else None
        if ws and any(i["token"] == token for i in ws.data.get("invites", [])):
            if not ws.is_member(user["uid"]):
                user = {**user, "_now": now}
                ws.add_member(user, role="member")
            return ws
    return None


def delete_workspace(wid: str) -> bool:
    d = ws_root() / wid
    if d.is_dir():
        shutil.rmtree(d)
        return True
    return False
