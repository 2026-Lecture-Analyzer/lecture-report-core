# 배포 가이드 — 강의력 분석 서비스 (AWS 소형 인스턴스 1대)

도메인 `lectureanalzer.yeseulkim.cloud` · 구글 로그인 · 워크스페이스(초대링크) · BYO API 키.

## 구성
```
인터넷 → Caddy(:443, 자동TLS) → Streamlit app(:8503) → /data 볼륨(워크스페이스 보고서)
```
- **컴퓨트**: Lightsail 2GB 또는 EC2 t4g.small/medium(ARM, 저렴). KoNLPy(JVM)·임베딩 때문에 **2GB+ 권장**.
- **키**: 사용자가 로그인 후 본인 Upstage/Gemini 키 입력 → **세션 메모리에만**(미저장).
- **데이터**: 워크스페이스별 격리 + 용량제한(`LECTURE_QUOTA_MB`, 기본 200MB). `/data` 볼륨에 영속.
- 🔒 **김영아 강사 데이터는 배포 안 됨** — `.dockerignore` 가 `reports/`·`AI_Lecture_Analysis_Report_Generator/` 제외.

## 1) 구글 OAuth 클라이언트 만들기
1. Google Cloud Console → 사용자 인증 정보 → **OAuth 2.0 클라이언트 ID(웹)**
2. 승인된 리디렉션 URI: `https://lectureanalzer.yeseulkim.cloud/oauth2callback`
3. `core/.streamlit/secrets.toml.example` → `secrets.toml` 로 복사 후 client_id/secret/cookie_secret 채우기
   - `cookie_secret`: `python -c "import secrets;print(secrets.token_hex(32))"`

## 2) AWS 인스턴스 + DNS
1. Lightsail/EC2 인스턴스 생성(Ubuntu, ARM t4g.small+), **고정 IP** 할당
2. 보안그룹: 80/443 인바운드 오픈
3. DNS: `lectureanalzer.yeseulkim.cloud` A레코드 → 인스턴스 공인 IP
4. 인스턴스에 Docker + Compose 설치

## 3) 배포
```bash
# 인스턴스에서 (core/ 디렉토리 기준)
cd core
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml logs -f
```
Caddy 가 Let's Encrypt 인증서를 자동 발급 → `https://lectureanalzer.yeseulkim.cloud` 접속.

## 4) 로컬에서 멀티테넌트 테스트(OIDC 없이)
```bash
cd core
LECTURE_DEV_USER=me@test.com .venv/bin/streamlit run service/app.py --server.port 8503
```
`LECTURE_DEV_USER` 가 있으면 구글 OIDC 없이 가짜 로그인 → 워크스페이스/초대/용량 흐름 확인 가능.

## 비용 가늠(저트래픽)
- Lightsail 2GB: **월 ~$12** (고정). EC2 t4g.small 온디맨드 ~$12, 1년 예약 시 ~$7.
- 데이터 전송·스토리지는 소량이면 무시 가능. LLM 비용은 **사용자 키로 청구**(서버 부담 0).

## 배포 전 점검(미검증 항목)
- **KoNLPy/JVM (Linux)**: `core/src/config.py` 의 JVM 경로 해석이 macOS(`libjvm.dylib`) 기준일 수 있음.
  Linux 컨테이너에선 `JAVA_HOME=/usr/lib/jvm/default-java` 로 잡았으나, 첫 분석 실행 시 JPype 로드 로그 확인 필요.
- **임베딩 백엔드**: 비용·서버부하를 줄이려면 사용자 키의 **API 임베딩(upstage)** 사용 권장(로컬 KURE 모델 다운로드 회피).
- **동시 분석**: 단일 인스턴스라 분석이 CPU를 오래 점유. 동시 사용자가 늘면 작업 큐/워커 분리 검토.
