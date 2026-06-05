# 🎓 Lecture Analyzer — AI 강의 분석 리포트 생성기

> STT로 추출한 강의 스크립트를 LLM으로 분석해, 강사의 **강의력을 다각도로 평가**하고 개선 인사이트를 담은 리포트를 자동 생성하는 시스템

NLP 과제 1 · AI 엔지니어 자연어처리과정 · 4인 1팀 · 4주 프로젝트

---

## 📌 프로젝트 개요

강의 STT 스크립트를 입력받아, 내부 **강의 품질 평가 체크리스트(5개 카테고리 · 18개 항목)** 를 기준으로
LLM 프롬프트 분석을 수행하고 강의력 스코어와 개선 코칭이 담긴 리포트를 출력합니다.

- **입력**: 강의 스크립트(`.txt`), 강의 메타데이터(`.csv`)
- **분석 엔진**: 체크리스트 항목별 LLM 프롬프트 → 항목 점수 + 근거 추출
- **출력**: 강의별 분석 리포트 + 강사별 비교 + 주차별 추이 (대시보드 / PDF)

---

## ✨ 주요 기능

| 기능 | 설명 |
|---|---|
| 텍스트 전처리 | STT 스크립트 정제, 발화 단위 분할, 메타데이터 매핑 |
| 항목별 LLM 분석 | 체크리스트 18개 항목을 프롬프트화하여 자동 평가 |
| 강의력 스코어링 | 카테고리별 가중 점수 → 종합 강의력 스코어 산출 |
| 강사 비교 분석 | 강사·과목별 강의력 비교 |
| 시계열 추이 | 주차별 강의력 변화 추이 시각화 |
| 리포트 생성 | 비개발자도 이해 가능한 리포트 자동 출력(PDF/DOCX/대시보드) |

---

## 🗂️ 디렉터리 구조

```
lecture-analyzer/
├── README.md                              # (현재 파일) 프로젝트 문서
├── .gitignore                             # 데이터·키·아티팩트 제외 설정
├── .env.example                           # 환경 변수 템플릿 (키 값은 비움)
├── src/                                   # 분석 파이프라인 소스
│   ├── config.py                          #   경로·상수·병합/모델 파라미터·JVM 설정
│   ├── manifest.py                        #   재현성 manifest(깃·버전·해시·설정)
│   ├── preprocess/                        #   전처리 (Step 0~2, 규칙·GPU 불필요)
│   │   ├── parse.py                       #     Step1: txt → raw.jsonl
│   │   ├── merge.py                       #     Step2: 화자매핑+발화병합 → merged.jsonl
│   │   ├── loader.py                      #     (EDA용) STT → DataFrame
│   │   └── text.py                        #     (EDA용) 토큰화·필러 분석(KoNLPy)
│   ├── refine/                            #   정제 (Step 3~5, 모델·Colab) — P1
│   │   ├── sectionize.py                  #     블록 → 큰 섹션(맥락 보존)
│   │   ├── glossary.py                    #     Step3: 용어집(규칙치환+모델후보)
│   │   ├── refine.py                      #     Step4: Solar 정제(체크포인트/재개)
│   │   ├── chunk.py                       #     Step5: 주제 단위 청킹
│   │   ├── prompts.py / jsonout.py        #     프롬프트 / 모델출력 JSON 파싱
│   │   └── model.py                       #     Solar-10.7B 로더/generate_fn
│   ├── analyze/                           #   분석 엔진 (P2) — 체크리스트 18항목 LLM 평가
│   │   ├── checklist.py                   #     18항목 정의(진실원천)
│   │   ├── prompts.py / engine.py         #     항목 프롬프트 / chunks→analysis.jsonl
│   ├── scoring/                           #   스코어링·검증 (P3)
│   │   ├── scoring.py                     #     카테고리 가중→종합점수
│   │   └── evaluate.py                    #     메타데이터(정답) 기반 검증
│   ├── report/                            #   리포트·대시보드 (P4)
│   │   ├── build.py                       #     강의별 리포트(MD→PDF/DOCX)
│   │   └── dashboard.py                   #     Streamlit 대시보드 스텁
│   └── eda/report.py                      #   EDA 통계·차트·리포트 엔진
├── scripts/
│   ├── run_preprocess.py                  # Step 0~2 실행(로컬, GPU 불필요)
│   ├── run_eda.py                         # EDA 리포트 실행
│   └── smoke_refine.py                    # Step 3~5 배관 스모크 테스트(모델 stub)
├── notebooks/
│   ├── 01_eda.ipynb                       # 인터랙티브 EDA
│   └── 02_refine_colab.ipynb             # Colab(A100): Step 3~5 정제 파이프라인
├── requirements.txt                       # 로컬(전처리·EDA) — 버전 고정
├── requirements-colab.txt                 # Colab(모델 추론) — 버전 고정
├── outputs/                               # ⛔ 산출물 (git 미포함)
│   ├── eda/                               #   eda_report.md + figures/
│   └── processed/                         #   raw/merged.jsonl, speaker_map, manifest
└── AI_Lecture_Analysis_Report_Generator/  # ⛔ 제공 데이터 (git 미포함, 로컬 전용)
```

> ⚠️ `AI_Lecture_Analysis_Report_Generator/` 는 제공 데이터·기본 README·체크리스트를 담고 있으며
> **`.gitignore`에 의해 저장소에 포함되지 않습니다.** 로컬에서만 사용하세요.

---

## 🚀 시작하기

```bash
# 1. 가상환경 (Python 3.13 권장 — 3.14 alpha는 패키지 호환 이슈)
python3.13 -m venv .venv && source .venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경 변수 설정 (.env.example 복사 후 키 입력)
cp .env.example .env   # OPENAI_API_KEY / ANTHROPIC_API_KEY

# 4. EDA 리포트 생성
python -m scripts.run_eda
#   → outputs/eda/eda_report.md + figures/*.png 생성
```

> 제공 데이터는 저장소에 포함되지 않으므로, 로컬 `AI_Lecture_Analysis_Report_Generator/` 폴더에
> 원본 데이터를 직접 배치한 뒤 실행하세요.

### KoNLPy(형태소 분석) 주의

KoNLPy는 **Java(JDK)** 가 필요합니다. JPype 최신 버전과 JDK 조합에서 JVM 경로 탐지 버그가 있어,
[src/config.py](src/config.py)의 `resolve_jvm_path()`가 `JAVA_HOME` 또는 `/usr/libexec/java_home`에서
경로를 직접 찾아 넘깁니다. Java가 없으면 EDA의 키워드/필러 분석만 건너뛰고 나머지는 정상 생성됩니다.

### 📊 EDA 주요 발견

- **STT 타임스탬프는 12시간제(AM/PM 미표기)** → 01~05시를 13~17시로 보정 처리.
- **메타데이터 과목명과 실제 강의 내용이 불일치** — 메타는 HTML/React/HTTP인데
  실제 발화는 Java IO·SQL/DB(테이블·조인·인덱스). `subject`를 정답 라벨로 신뢰 불가.
- 음성 인식 오류 다수(예: '잡바'=Java) → 도메인 용어 정규화 사전 필요.
- 자세한 내용은 `outputs/eda/eda_report.md`(로컬 생성) 참고.

---

## 🔧 전처리·정제 파이프라인

원본 STT를 LLM 분석에 쓸 수 있는 형태로 가공한다. **원칙 2가지: ① 모델은 Step 3~5에만(1~2는 규칙)
② 원본 불변 + `raw_ref`로 타임스탬프까지 추적.**

```
txt ─①파싱─► raw.jsonl ─②화자매핑+병합─► merged.jsonl
                                            │  (여기까지 로컬, GPU 불필요)
        ┌───────────────────────────────────┘
        ▼ (Colab A100, Solar-10.7B)
   ③용어집 ─► ④섹션 정제 ─► clean.jsonl ─► ⑤주제 청킹 ─► chunks.jsonl
```

| 단계 | 방식 | 입력 → 출력 | 실행 위치 |
|---|---|---|---|
| ① 파싱 | 규칙 | txt → `raw.jsonl` | 로컬 |
| ② 화자매핑+병합 | 규칙 | raw → `merged.jsonl` (+`speaker_map.json`) | 로컬 |
| ③ 용어집 | 모델 | merged → `glossary_candidates.json` → 검수 → `glossary.json` | Colab |
| ④ 정제 | 모델(Solar) | merged+용어집 → `clean.jsonl` | Colab |
| ⑤ 청킹 | 모델 | clean → `chunks.jsonl` (분석부 입력) | Colab |

### 로컬: Step 0~2 (GPU 불필요)

```bash
python -m scripts.run_preprocess     # raw.jsonl, merged.jsonl, speaker_map.json, manifest
python -m scripts.smoke_refine       # (선택) Step 3~5 배관 점검 — 모델 없이 stub로
```

### Colab: Step 3~5 (A100 · Solar-10.7B)

1. 로컬 산출물 `outputs/processed/merged.jsonl` 을 Google Drive `MyDrive/lecture-analyzer/` 에 업로드
2. [notebooks/02_refine_colab.ipynb](notebooks/02_refine_colab.ipynb) 를 Colab에서 열고 런타임 **A100**로 설정 후 순서대로 실행
3. 산출물(`clean.jsonl`, `chunks.jsonl`)은 Drive에 **1건씩 체크포인트** 저장 — 런타임이 끊겨도 해당 셀만 재실행하면 이어서 재개

> 코드는 repo에서, **데이터는 Drive에서**(분리). 데이터·정제 산출물은 git/공개 업로드 금지.

### 설계 메모

- **화자 매핑은 파일(일자)별** — 해시 ID가 세션마다 바뀜. `speaker_map.json`은 수동 보정 가능.
- **병합 임계값 20초** — 측정 결과 동일화자 연속 gap 중앙값 10초, 81%가 ≤15초. 원안의 2~3초는 과분할이라 상향([src/config.py](src/config.py)에서 조정).
- **용어집 2종** — `rule:true` 항목은 모델 호출 전 결정적 치환, 나머지는 모델이 처리.
- **재현성** — 패키지/모델 버전 고정([requirements.txt](requirements.txt), [requirements-colab.txt](requirements-colab.txt)), 모델 `revision` 핀 권장(config), 그리디 디코딩+시드 고정, 산출물마다 `manifest`(깃 커밋·버전·입력 해시) 동봉.
- **모델 주입(`generate_fn`)** — 파이프라인 로직과 모델을 분리해, GPU 없이도 `smoke_refine.py`로 배관 검증.

---

## 📐 분석 → 스코어링 → 리포트 (다음 단계)

`chunks.jsonl` 이후 단계. 단계 간 인터페이스는 **[docs/SCHEMA.md](docs/SCHEMA.md)** 의 JSONL 계약을 따른다.

| 단계 | 모듈 | 입력 → 출력 |
|---|---|---|
| 분석(18항목) | `src/analyze/` | `chunks.jsonl` → `analysis.jsonl` |
| 스코어링·검증 | `src/scoring/` | `analysis.jsonl` + 메타(정답) → `scores.json` |
| 리포트·대시보드 | `src/report/` | `scores.json` → 강의별 리포트 / Streamlit |

> ⚠️ **메타데이터는 정답/검증 전용** — 분석 input(모델 프롬프트)에 넣지 않는다.

**4인 역할 분담**: [docs/TEAM.md](docs/TEAM.md) (P1 정제 / P2 분석 / P3 스코어링·검증 / P4 리포트·인프라).

---

## 🛠️ 기술 스택

| 구분 | 도구 |
|---|---|
| LLM | OpenAI GPT-4o / Claude API |
| NLP 프레임워크 | LangChain / LlamaIndex |
| 데이터 처리 | Python (pandas, KoNLPy) |
| 시각화 / 대시보드 | Streamlit / Gradio |
| 문서 생성 | ReportLab / python-docx |

---

## 👥 팀 · 역할 분담

> 규칙 기반 전처리(Step 0~2)는 완료·검증됨. 아래는 **고도화 단계** 분담.
> 단계 간 인터페이스(JSONL 계약)는 **[docs/SCHEMA.md](docs/SCHEMA.md)** — 이것만 지키면 4명이 병렬로 진행.

| 역할 | 워크스트림 | 실행 | 담당 폴더 | 입력 → 산출물 | 이름 |
|---|---|---|---|---|---|
| **P1** | 정제 고도화 | 🔴 Colab(Solar) | `src/refine/` | `merged.jsonl` → `clean.jsonl`, `chunks.jsonl` | (작성 예정) |
| **P2** | 분석 엔진 | 🔴 Colab(LLM) | `src/analyze/` | `chunks.jsonl` → `analysis.jsonl` | (작성 예정) |
| **P3** | 스코어링·검증 | 🟢 로컬 | `src/scoring/` | `analysis.jsonl` + 메타(정답) → `scores.json` | (작성 예정) |
| **P4** | 리포트·대시보드·인프라 | 🟢 로컬 | `src/report/` | `scores.json` → 리포트/대시보드 | (작성 예정) |

**P1 — 정제 고도화 (Colab)**
- Colab에서 Solar-10.7B 실제 구동, 정제 프롬프트 튜닝(군더더기 제거 품질)
- 용어집 후보 추출→검수→`glossary.json` 확정, `rule:true` 항목 정리
- 청킹 고도화: LLM 분할 → 임베딩(sentence-transformers) 기반 주제경계 검토
- 정제 전/후 품질 지표(필러 감소율 등) 측정

**P2 — 분석 엔진 (Colab)**
- 체크리스트 18항목(`src/analyze/checklist.py`)별 프롬프트 정교화 + few-shot
- 강의별 항목 평가 → `analysis.jsonl`(근거 인용 `chunk_id` 포함)
- 토큰 초과 대비: 항목별 관련 청크 선별(임베딩 검색), self-consistency 옵션
- ⚠️ 실제 체크리스트 PDF의 세부 기준을 `checklist.py` description에 반영

**P3 — 스코어링·검증 (로컬)**
- `scoring.py`: 카테고리 가중→종합점수, `CATEGORY_WEIGHTS` 확정
- 강사/세션 비교, 주차별 시계열 추이
- `evaluate.py`: **메타데이터를 정답으로** 분석 정확도 검증 (⚠️ 메타는 input 금지, 검증 전용)

**P4 — 리포트·대시보드·인프라 (로컬)**
- `build.py`: 강의별 리포트(MD→PDF/DOCX), `dashboard.py`: Streamlit 대시보드
- 재현성/CI: manifest, 버전 핀, repo 브랜치·PR 운영, 발표자료/시연영상

**중간점검(2주차) 정렬**: 단일 강의 1편 end-to-end — P1 정제 → P2 18항목 분석 → P3 점수 1건 → P4 리포트/시연.

> 각 모듈에 `TODO(P#)` 주석으로 다음 작업 표시. 전체 상세: [docs/TEAM.md](docs/TEAM.md)

---

## 🔒 데이터 보안 (필독)

제공 데이터는 **실제 강의 스크립트**를 포함하므로 아래를 반드시 준수합니다.

- 프로젝트 목적 외 사용 및 외부 공유 **금지**
- 개인 클라우드 · SNS 등 외부 업로드 **금지**
- **원본 데이터 GitHub 커밋 금지** → `.gitignore`로 `AI_Lecture_Analysis_Report_Generator/` 전체 제외 처리됨
- API 키는 `.env`에만 보관하며 커밋하지 않음
- 프로젝트 종료 후 모든 제공 데이터 **파기** 및 파기 확인서 제출

> 작업 전, 원본 데이터가 `git status`에 잡히지 않는지 반드시 확인하세요.
