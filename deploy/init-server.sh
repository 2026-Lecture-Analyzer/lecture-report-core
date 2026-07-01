#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# 강의분석기 배포 서버 1회 초기세팅.
#   - Docker + compose 플러그인 설치
#   - 현재 유저를 docker 그룹에 추가(sudo 없이 docker 실행 → 배포 워크플로가 씀)
#   - 배포용 SSH 키 생성 + authorized_keys 등록
#   - 마지막에 GitHub Environment 에 넣을 값 3개 출력
#
# 사용법(새로 만든 서버에 ssh 접속 후):
#   bash init-server.sh
# 지원 OS: Ubuntu/Debian(apt), Amazon Linux/RHEL 계열(dnf·yum)
# ────────────────────────────────────────────────────────────────
set -euo pipefail

echo "== 강의분석기 배포 서버 초기세팅 =="

# --- 1. Docker 설치 ------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  echo "[1/4] Docker 이미 설치됨 — 건너뜀"
else
  echo "[1/4] Docker 설치 중..."
  if command -v apt-get >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sudo sh
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y docker
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y docker
  else
    echo "!! 지원 안 되는 OS입니다. Docker 를 수동 설치하세요: https://docs.docker.com/engine/install/" >&2
    exit 1
  fi
  sudo systemctl enable --now docker
fi

# compose 플러그인 확인(없으면 설치)
if ! docker compose version >/dev/null 2>&1; then
  echo "  docker compose 플러그인 설치 중..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y docker-compose-plugin
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y docker-compose-plugin || true
  fi
  docker compose version >/dev/null 2>&1 || {
    echo "!! docker compose 플러그인 설치 실패 — 수동 설치 필요." >&2; exit 1; }
fi

# --- 2. docker 그룹에 현재 유저 추가 -------------------------------
echo "[2/4] '$USER' 를 docker 그룹에 추가(sudo 없이 docker 실행)"
sudo usermod -aG docker "$USER"

# --- 3. 배포용 SSH 키 생성 & authorized_keys 등록 ------------------
echo "[3/4] 배포용 SSH 키 준비"
KEY="$HOME/.ssh/lecture_deploy"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
if [ -f "$KEY" ]; then
  echo "  기존 키 재사용: $KEY"
else
  ssh-keygen -t ed25519 -N "" -C "github-actions-deploy" -f "$KEY"
fi
# 공개키를 authorized_keys 에 등록(중복 방지)
touch "$HOME/.ssh/authorized_keys"
grep -qxF "$(cat "$KEY.pub")" "$HOME/.ssh/authorized_keys" \
  || cat "$KEY.pub" >> "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"

# --- 4. 접속 정보 수집 & 출력 --------------------------------------
echo "[4/4] 접속 정보 수집"
IP="$(curl -fsS --max-time 5 https://checkip.amazonaws.com 2>/dev/null \
      || curl -fsS --max-time 5 ifconfig.me 2>/dev/null \
      || echo '<서버_공인_IP_직접_확인>')"

cat <<INFO

============================================================
✅ 세팅 완료! 아래 값을 GitHub 관리자(예슬)에게 전달하세요.
   등록 위치: GitHub → repo Settings → Environments → deploy/<본인이름>

[Secrets 로 등록]
  DEPLOY_HOST   = ${IP}
  DEPLOY_USER   = ${USER}
  DEPLOY_SSH_KEY:
------------------------------------------------------------
$(cat "$KEY")
------------------------------------------------------------

[Variables 로 등록]
  DEPLOY_DOMAIN = (본인이 쓸 도메인, 예: myapp.example.com)
  ※ 구글 로그인 쓰면 STREAMLIT_SECRETS_TOML(Secret)도 본인 도메인용으로 별도 등록

──────────────── ⚠️ 반드시 확인 ────────────────
 1) 위 DEPLOY_SSH_KEY(개인키)는 공개 채널(단톡 등)에 올리지 말 것 — DM/1:1로만.
 2) 서버 보안그룹/방화벽에서 인바운드 22·80·443 포트 허용.
 3) 도메인 A레코드를 ${IP} 로 연결해야 HTTPS 자동발급됨.
 4) (AWS면) 재부팅해도 IP 안 바뀌게 Elastic IP 권장.
============================================================
INFO
