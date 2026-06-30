# Lecture Analyzer — AI 강의 분석 리포트 생성기 (core)

> STT 강의 스크립트를 LLM으로 분석해 강사의 강의력을 18개 항목으로 평가하고, 근거와 개선점을 리포트로 자동 생성하는 시스템.

- 서비스: **https://lectureanalzer.yeseulkim.cloud/**
- 시연 영상: **https://www.youtube.com/watch?v=rOUDMiKr6xk**
- 성능 평가: **https://github.com/2026-Lecture-Analyzer/eval**

NLP 과제 1 · 4인 1팀 · 4주 프로젝트. 본 저장소(core)는 분석 파이프라인 + 서비스(앱)·배포를 담습니다.

---

## 개요

강의 STT 스크립트(또는 녹음/영상)를 입력받아, 강의 품질 체크리스트(5영역·18항목) 기준으로 채점하고,
각 점수의 근거 문장(타임스탬프 포함)과 개선 우선순위가 담긴 리포트를 웹 대시보드·PDF로 제공합니다.

- 입력: 강의 스크립트(`.txt`) 또는 녹음/영상(자동 STT)
- 분석: 정량 4항목(규칙 메트릭) + 나머지 14항목(holistic LLM, self-consistency)
- 출력: 강의별 리포트 · 강사 코칭 · 수강생 피드백 비교 (대시보드 / PDF)

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 다양한 입력 | 텍스트 + 녹음/영상(Gemini STT 자동 전사) |
| 하이브리드 분석 | 정량 메트릭(결정적) + holistic LLM 채점, 점수와 근거 분리 생성(환각 방지) |
| 분석 대시보드 | 종합 점수·레이더·주차 추이·오전/오후 비교·항목별 근거 |
| 강사 코칭 | 다회차 종합 + AI 코칭(진단·개선법·예시 멘트) |
| 수강생 피드백 | 공개 설문(토큰 URL)으로 실제 수강생 평가 수집·집계 |
| AI vs 학생 | AI 평가와 수강생 평가 항목별 비교 |
| 리포트 출력 | 비개발자용 PDF 리포트(요약표·레이더·근거 인용) 원클릭 |
| 멀티테넌트 | 구글 로그인·워크스페이스·초대, BYO 키(세션에만 보관) |

---

## 주요 화면

### 분석 대시보드
종합 강의력 점수와 레이더 차트로 5개 영역의 강·약점을 한눈에 보고, 18개 항목의 점수·개선 우선순위를 확인합니다.

![분석 대시보드](docs/images/02_대시보드.png)

항목별 근거 카드 — 각 점수마다 "왜 그 점수인지"를 강의 속 실제 발언으로 제시합니다.

![항목별 근거 카드](docs/images/02_대시보드_근거카드.png)

강의 원문 하이라이트 — 근거가 된 발언을 원문 위에서 바로 확인합니다.

![강의 원문 하이라이트](docs/images/02_대시보드_하이라이트.png)

### 강사 코칭 · 수강생 피드백 · AI vs 학생

| 강사 코칭 | 수강생 피드백 설문 | AI vs 학생 비교 |
|:---:|:---:|:---:|
| ![강사 코칭](docs/images/03_강사코칭.png) | ![수강생 피드백](docs/images/04_수강생설문폼.png) | ![AI vs 학생](docs/images/05_AI_vs_학생.png) |
| 다회차 종합 + AI 코칭 멘트 | 공개 설문으로 실제 평가 수집 | AI 평가와 수강생 체감 격차 |

### 강의 업로드 · PDF 리포트

| 강의 분석 추가(업로드) | PDF 리포트 |
|:---:|:---:|
| ![분석 추가](docs/images/01_분석추가_업로드.png) | ![PDF 리포트](docs/images/06_PDF리포트.png) |

---

## 빠른 시작

```bash
# 1) 가상환경 (Python 3.13)
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) 서비스 실행 (로컬, 구글 OIDC 없이 개발 로그인)
LECTURE_DEV_USER=me@test.com .venv/bin/streamlit run service/app.py --server.port 8503
#   -> http://localhost:8503

# 3) (선택) 전처리·EDA만
python -m scripts.run_preprocess     # txt -> raw/merged.jsonl, speaker_map
python -m scripts.run_eda            # EDA 리포트
```

- 분석에는 사용자 API 키(Upstage Solar 또는 Google Gemini)가 필요합니다 — 화면에서 입력(세션에만 보관).
- 배포 서비스는 https://lectureanalzer.yeseulkim.cloud/ 에서 바로 사용 가능합니다.

---

## 분석 파이프라인

원본 STT를 분석 가능한 형태로 가공 -> 18항목 채점 -> 리포트. 원칙: (1) 규칙으로 끝낼 건 규칙으로(모델은 정제·분석에만) (2) 원본 불변 + `raw_ref`로 타임스탬프까지 역추적 (3) 단계마다 manifest로 재현성.

```mermaid
flowchart TD
    IN["강의 STT txt<br/>(또는 녹음/영상 -> STT)"]
    subgraph PREP["전처리 · 규칙 · 로컬"]
        S1["1. 파싱 parse.py<br/>12->24시간 보정"] --> RAW[("raw.jsonl")]
        RAW --> S2["2. 화자매핑·병합 merge.py"] --> MERGED[("merged.jsonl")]
    end
    subgraph REFINE["정제 · 모델"]
        MERGED --> S3["3. 용어집 glossary.py"] --> S4["4. 정제 refine.py(Solar)"] --> CLEAN[("clean.jsonl")]
        CLEAN --> S5["5. 청킹 chunk.py + 항목별 임베딩 태깅"] --> CHUNKS[("chunks.jsonl")]
    end
    subgraph ANALYZE["분석 -> 점수 -> 리포트"]
        CHUNKS --> S6["6. 하이브리드 평가 analyze/hybrid.py<br/>정량 4 + holistic 14"] --> ANAL[("analysis.jsonl<br/>점수 + 근거")]
        ANAL --> S7["7. 스코어링 scoring.py<br/>카테고리 가중 -> 0~100"] --> S8["8. 리포트 / 대시보드 / PDF"]
    end
```

| 단계 | 방식 | 입력 -> 출력 | 모듈 |
|---|---|---|---|
| 1. 파싱 | 규칙 | txt -> `raw.jsonl` | `preprocess/parse.py` |
| 2. 화자매핑·병합 | 규칙 | raw -> `merged.jsonl` | `preprocess/merge.py` |
| 3. 용어집 | 모델+검수 | merged -> `glossary.json` | `refine/glossary.py` |
| 4. 정제 | 모델(Solar) | 섹션+용어집 -> `clean.jsonl` | `refine/refine.py` |
| 5. 청킹·태깅 | 모델+임베딩 | clean -> `chunks.jsonl` | `refine/chunk.py` |
| 6. 하이브리드 평가 | 규칙+LLM | chunks -> `analysis.jsonl` | `analyze/hybrid.py` |
| 7. 스코어링 | 규칙 | analysis -> `scores.json` | `scoring/scoring.py` |
| 8. 리포트 | 규칙 | scores -> 대시보드/PDF | `report/`, `service/` |

핵심 설계
- 점수와 근거 분리: 점수는 holistic LLM(self-consistency 중앙값), 근거 문장은 항목별 임베딩 태깅 top-k로 별도 부착 -> 환각 방지·항목 정합.
- 결정적 4항목(반복·완결성·일관성·발화속도)은 규칙 메트릭으로 덮어써 안정성 확보.
- 재현성: 패키지/모델 버전 고정, 산출물마다 manifest(깃 커밋·해시), 정제는 섹션 단위 체크포인트·재개.

단계 간 JSONL 인터페이스 계약: [docs/SCHEMA.md](docs/SCHEMA.md)

---

## 서비스 & 배포

- 앱: `service/` — Streamlit 멀티테넌트(구글 로그인·워크스페이스·BYO 키·작업 큐·PDF 다운로드).
- 배포: 소형 서버 1대 — `deploy/`(Docker Compose + Caddy 자동 TLS). AWS Lightsail 2GB / EC2 t4g.small 권장.

```bash
cd core && docker compose -f deploy/docker-compose.yml up -d --build
```

배포 서비스: https://lectureanalzer.yeseulkim.cloud/ · 자세한 가이드: [deploy/README.md](deploy/README.md)

---

## 인프라 비용 및 동시 처리

### 비용
비용은 사용량 기반 AI 분석 비용과 고정 인프라 비용으로 나뉜다. AI 비용은 사용자 키(BYO)로 사용한 만큼만 종량 과금된다.

| 구분 | 내용 |
|---|---|
| AI 분석 | 강의 1편당 약 50~200원(추정) — 전사 약 7천~1.7만 자 × self-consistency 3~5패스, 정량 4항목은 LLM 미사용 |
| 인프라(고정) | 소형 서버 1대 월 약 $12(≈₩16,000) · 예약 시 ~$7 · 스토리지 소액 |
| 월 운영비 예시 | 강의 30편/월 ≈ ₩2만 내외, 100편/월 ≈ ₩2만~3.6만 |

### 동시 처리 용량 (설계상 추정, 부하 테스트 전)
| 작업 | 동시 용량 | 병목 |
|---|---|---|
| 리포트 조회 | 동시 수십 명 수준 | Streamlit 세션 메모리(2GB) |
| 강의 분석(채점) | 사실상 1건씩 직렬(나머지 큐 대기) | BYO 키를 프로세스 전역에 주입 → 전역 락으로 직렬화 |

- 분석은 키 충돌 방지를 위해 전역 락으로 한 번에 하나씩 처리되며, 처리량은 강의 1편당 1~3분 기준 시간당 수십 편 수준 — 팀·부트캠프 규모의 저~중 동시성에 적합.
- 확장: (1) 호출 단위 키 전달로 전역 락 제거·분석 병렬화 (2) 임베딩·전처리 워커 분리 및 사양 상향 (3) 다중 인스턴스 + 로드밸런서.

---

## 성능

사람 정답 14개 강의로 검증(2트랙):
- 점수 정확도: 사람과 같은 방향 91% · 평균 오차 0.67(5점 만점)
- 근거 정확도: 항목 근거 제시율 94% · 환각 없음

상세·재현: https://github.com/2026-Lecture-Analyzer/eval

---

## 디렉터리 구조

```
core/
├── src/
│   ├── preprocess/     # 파싱·화자매핑·병합 (규칙)
│   ├── refine/         # 정제·청킹·항목별 임베딩 태깅 (Solar)
│   ├── analyze/        # 하이브리드 평가(holistic + 메트릭) · 18항목 프롬프트
│   ├── scoring/        # 카테고리 가중 -> 종합 점수
│   ├── report/         # 리포트 빌드 · PDF(ReportLab) · 대시보드
│   ├── stt/ feedback/  # STT 전사 · 수강생 피드백
│   └── eda/            # EDA 통계·차트
├── service/            # Streamlit 멀티테넌트 SaaS (app·auth·workspace·jobs·report_view)
├── deploy/             # Docker · Caddy · 배포 가이드
├── scripts/            # 실행·스모크 테스트
├── notebooks/          # EDA · Colab 정제
├── docs/               # SCHEMA · TEAM · images · readme_drafts(팀원 초안 아카이브)
├── requirements.txt    # 로컬
└── requirements-colab.txt
```

> 데이터·산출물(`outputs/`, `workspaces/`, `AI_Lecture_Analysis_Report_Generator/`, `reports/`)은 `.gitignore`로 제외.

---

## 기술 스택

| 구분 | 도구 |
|---|---|
| LLM | Upstage Solar(분석 기본) · Google Gemini(STT·옵션) |
| 임베딩 | API 임베딩(Upstage) / 로컬 모델 |
| 데이터 처리 | Python 3.13 · pandas · KoNLPy |
| 앱 / 시각화 | Streamlit · Plotly |
| 문서 생성 | ReportLab(PDF) |
| 배포 | Docker · Caddy(자동 TLS) · AWS |

---

## 팀

NLP 과제 1 · 4인 1팀. 강의 품질 체크리스트(18항목)를 영역별로 분담 설계 — C2 강의 구조 · C3 개념 설명 · C4 진행 방식 · C5 실습·적용. 상세: [docs/TEAM.md](docs/TEAM.md)

---

## 데이터 보안

제공 데이터는 실제 강의 스크립트를 포함하므로 반드시 준수합니다.

- 원본·정제·gold·분석 산출물 등 데이터 일체 커밋/외부 공유 금지(`.gitignore`로 차단)
- API 키는 `.env`/세션에만 보관, 커밋 금지
- 프로젝트 종료 후 제공 데이터 파기
- 특정 강사 실데이터(`reports/`)는 배포·커밋에서 제외(`.dockerignore`/`.gitignore`)

> 작업 전 `git status`에 데이터가 잡히지 않는지 확인하세요.
