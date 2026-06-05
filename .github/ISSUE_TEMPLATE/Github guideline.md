# GitHub 협업 가이드라인

> NLP 과제 1 — AI 강의 분석 리포트 생성기  
> 최초 작성일: 2026-02-02 | 전원 숙지 후 작업 시작

---

## 목차

1. [브랜치 전략](#1-브랜치-전략)
2. [커밋 컨벤션](#2-커밋-컨벤션)
3. [이슈 관리](#3-이슈-관리)
4. [PR 규칙](#4-pr-규칙)
5. [디렉토리 구조](#5-디렉토리-구조)

---

## 1. 브랜치 전략

### 브랜치 네이밍 규칙

```text
{기능}/{담당자}/{버전}
```

| 구성 요소 | 설명 | 예시 |
|---|---|---|
| 기능 | 작업 대상 기능명 | `preprocess`, `refine`, `analysis`, `scoring`, `report`, `eda`, `docs` |
| 담당자 | 본인 이니셜 (소문자) | `kys`, `ljs`, `팀원이니셜` |
| 버전 | 작업 버전 | `v1`, `v2`, `v3` |

### 기능명 기준표

| 기능명 | 해당 디렉토리/파일 | 설명 |
|---|---|---|
| `preprocess` | `src/preprocess/` | 파싱·화자매핑·발화병합 |
| `refine` | `src/refine/` | 용어집·정제·청킹 (Colab) |
| `analysis` | `src/analyze/` | 체크리스트 18항목 LLM 평가 |
| `scoring` | `src/scoring/` | 스코어링·검증 |
| `report` | `src/report/` | 리포트·대시보드 |
| `eda` | `src/eda/`, `notebooks/01_eda.ipynb` | EDA 분석 |
| `docs` | `docs/` | 문서 작업 |

### 브랜치 예시

```bash
preprocess/kys/v1   # 전처리 - kys - v1
refine/ljs/v1       # 정제 - ljs - v1
analysis/kys/v1     # 분석 엔진 - kys - v1
analysis/kys/v2     # 분석 엔진 - kys - v2 (개선)
scoring/ljs/v1      # 스코어링 - ljs - v1
report/kys/v1       # 리포트 - kys - v1
eda/ljs/v1          # EDA - ljs - v1
docs/kys/v1         # 문서 - kys - v1
```

### 브랜치 생성 방법

```bash
# 브랜치 생성 및 이동
git checkout -b preprocess/kys/v1

# 원격에 push
git push origin preprocess/kys/v1
```

### 브랜치 흐름

```text
main
 └── develop                    ← 통합 브랜치 (항상 동작 상태 유지)
      ├── preprocess/kys/v1     ← 기능 브랜치
      ├── refine/ljs/v1
      ├── analysis/kys/v1
      └── scoring/ljs/v1
```

> ⚠️ `main`에 직접 push 금지. 반드시 `develop` → PR → merge 순서로 진행

---

## 2. 커밋 컨벤션

### 커밋 메시지 형식

```text
{타입}: {내용}
```

### 타입 목록

| 타입 | 설명 | 예시 |
|---|---|---|
| `feature-preprocess` | 전처리 관련 새 기능 | `feature-preprocess: 슬라이딩 윈도우 구현` |
| `feature-refine` | 정제 관련 새 기능 | `feature-refine: Solar 정제 체크포인트 추가` |
| `feature-analysis` | 분석 관련 새 기능 | `feature-analysis: 체크리스트 항목별 프롬프트 작성` |
| `feature-scoring` | 스코어링 관련 새 기능 | `feature-scoring: 카테고리 가중치 계산 구현` |
| `feature-report` | 리포트 관련 새 기능 | `feature-report: PDF 출력 모듈 추가` |
| `feature-eda` | EDA 관련 새 기능 | `feature-eda: 시간대별 필러 분석 추가` |
| `fix` | 버그 수정 | `fix: 타임스탬프 자정 넘김 보정 오류 수정` |
| `refact` | 리팩토링 (기능 변경 없음) | `refact: parse_script 함수 모듈화` |
| `docs` | 문서 추가/수정 | `docs: 분석 기준 명세서 업데이트` |
| `test` | 테스트 코드 | `test: 화자 매핑 단위 테스트 추가` |
| `chore` | 설정, 패키지 등 기타 | `chore: requirements.txt 패키지 버전 고정` |
| `data` | 데이터 관련 (분석 결과 등) | `data: EDA 결과 추가` |

### 커밋 예시

```bash
# 좋은 예
git commit -m "feature-preprocess: parse.py 정규식 분해 및 화자 매핑 구현"
git commit -m "feature-preprocess: merge.py 발화 병합 gap 20초 기준 적용"
git commit -m "fix: 자정 넘김 타임스탬프 24시간 보정 로직 수정"
git commit -m "refact: parse_script 함수 loader.py로 분리"
git commit -m "feature-refine: glossary.py STT 오류 후보 추출 구현"
git commit -m "feature-analysis: checklist.py 18항목 프롬프트 초안 작성"
git commit -m "feature-eda: 시간대별 필러 단어 빈도 시각화 추가"
git commit -m "docs: GitHub 협업 가이드라인 최초 작성"
git commit -m "chore: requirements.txt 패키지 버전 고정"

# 나쁜 예 ❌
git commit -m "수정"
git commit -m "작업중"
git commit -m "ㅇㅇ"
git commit -m "update"
git commit -m "fix"
```

### 커밋 규칙

- 한 커밋 = 한 작업 단위 (여러 기능을 한 번에 커밋 ❌)
- 한국어로 작성 권장
- 내용은 **무엇을 했는지** 명확하게

---

## 3. 이슈 관리

### 이슈 네이밍 형식

```text
[타입] 제목
```

### 이슈 타입

| 타입 | 설명 |
|---|---|
| `[FEAT]` | 새로운 기능 개발 |
| `[FIX]` | 버그 수정 |
| `[DOCS]` | 문서 작업 |
| `[REFACT]` | 리팩토링 |
| `[DISCUSS]` | 팀 논의 필요 사항 |
| `[DATA]` | 데이터 관련 |

### 이슈 예시

```text
[FEAT] 슬라이딩 윈도우 전처리 구현
[FIX] 타임스탬프 자정 넘김 오류
[DISCUSS] 분석 항목별 가중치 결정 필요
[DOCS] 분석 기준 명세서 작성
[DATA] EDA 리포트 결과 공유
```

### 이슈 작성 템플릿

```markdown
## 작업 내용
> 무엇을 할 것인지 간단히 설명

## 상세 내용
-

## 완료 기준 (Definition of Done)
- [ ]

## 관련 브랜치
`기능/담당자/버전`

## 참고 사항
```

### 이슈 라벨

| 라벨 | 색상 | 설명 |
|---|---|---|
| `feature` | 🟢 초록 | 기능 개발 |
| `bug` | 🔴 빨강 | 버그 |
| `documentation` | 🔵 파랑 | 문서 |
| `discussion` | 🟡 노랑 | 논의 필요 |
| `in-progress` | 🟠 주황 | 작업 중 |
| `review-needed` | 🟣 보라 | 리뷰 요청 |

---

## 4. PR 규칙

### PR 네이밍

```text
[타입] 제목 (브랜치명)
예시: [FEAT] 슬라이딩 윈도우 구현 (preprocess/kys/v1)
```

### PR 템플릿

```markdown
## 작업 내용
> 이번 PR에서 무엇을 했는지 간단히 설명

## 변경 사항
-

## 테스트 방법
# 실행 방법 작성

## 관련 이슈
closes #이슈번호

## 리뷰 포인트
> 리뷰어가 특히 봐줬으면 하는 부분
```

### PR 규칙

- `develop` 브랜치로만 PR (main 직접 PR 금지)
- 최소 1명 이상 리뷰 승인 후 merge
- PR 올리면 팀 카톡/슬랙에 공유
- 셀프 merge 금지

---

## 5. 디렉토리 구조

```text
lecture-analyzer/
├── README.md
├── .gitignore
├── .env.example
├── docs/
│   └── github-guidelines/
├── src/
│   ├── config.py
│   ├── manifest.py
│   ├── preprocess/
│   │   ├── parse.py
│   │   ├── merge.py
│   │   ├── loader.py
│   │   └── text.py
│   ├── refine/
│   │   ├── sectionize.py
│   │   ├── glossary.py
│   │   ├── refine.py
│   │   ├── chunk.py
│   │   ├── prompts.py
│   │   ├── jsonout.py
│   │   └── model.py
│   ├── analyze/
│   │   ├── checklist.py
│   │   ├── prompts.py
│   │   └── engine.py
│   ├── scoring/
│   │   ├── scoring.py
│   │   └── evaluate.py
│   ├── report/
│   │   ├── build.py
│   │   └── dashboard.py
│   └── eda/
│       └── report.py
├── scripts/
│   ├── run_preprocess.py
│   ├── run_eda.py
│   └── smoke_refine.py
├── notebooks/
│   ├── 01_eda.ipynb
│   └── 02_refine_colab.ipynb
├── requirements.txt
├── requirements-colab.txt
├── outputs/              ⛔ git 미포함
└── AI_Lecture_Analysis_Report_Generator/  ⛔ git 미포함
```

### 파일별 설명

| 경로 | 설명 |
|---|---|
| `src/config.py` | 경로·상수·모델 파라미터·JVM 설정 |
| `src/manifest.py` | 재현성 manifest (깃·버전·해시) |
| `src/preprocess/parse.py` | Step1: txt → raw.jsonl |
| `src/preprocess/merge.py` | Step2: 화자매핑 + 발화병합 → merged.jsonl |
| `src/preprocess/loader.py` | (EDA용) STT → DataFrame |
| `src/preprocess/text.py` | (EDA용) 토큰화·필러 분석 (KoNLPy) |
| `src/refine/sectionize.py` | 블록 → 섹션 (맥락 보존) |
| `src/refine/glossary.py` | Step3: 용어집 (규칙치환 + 모델후보) |
| `src/refine/refine.py` | Step4: 모델 정제 (체크포인트/재개) |
| `src/refine/chunk.py` | Step5: 주제 단위 청킹 |
| `src/refine/model.py` | 모델 로더 / generate_fn |
| `src/analyze/checklist.py` | 18항목 정의 (진실원천) |
| `src/analyze/engine.py` | chunks → analysis.jsonl |
| `src/scoring/scoring.py` | 카테고리 가중 → 종합점수 |
| `src/scoring/evaluate.py` | 메타데이터(정답) 기반 검증 |
| `src/report/build.py` | 강의별 리포트 (MD → PDF/DOCX) |
| `src/report/dashboard.py` | Streamlit 대시보드 |
| `src/eda/report.py` | EDA 통계·차트·리포트 엔진 |
| `scripts/run_preprocess.py` | Step 0~2 실행 (로컬, GPU 불필요) |
| `scripts/run_eda.py` | EDA 리포트 실행 |
| `scripts/smoke_refine.py` | Step 3~5 배관 스모크 테스트 |

### .gitignore 필수 항목

```text
# 강의 원본 데이터 (절대 커밋 금지)
AI_Lecture_Analysis_Report_Generator/
outputs/
*.txt
*.csv

# 분석 산출물
*.jsonl
*.json

# 환경 변수
.env

# Python
__pycache__/
*.pyc

# Jupyter
.ipynb_checkpoints/

# OS
.DS_Store
```

---

## 빠른 시작 체크리스트

```text
□ 레포 clone
□ 본 가이드라인 숙지
□ 담당 기능 이슈 생성
□ 브랜치 생성 (기능/이니셜/v1)
□ 작업 시작
□ 커밋 컨벤션 지켜서 커밋
□ PR 생성 → 팀 공유 → 리뷰 → merge
```

---
