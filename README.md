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
│   ├── preprocess/                        #   전처리
│   ├── analyze/                           #   LLM 프롬프트 분석
│   ├── scoring/                           #   강의력 스코어링
│   └── report/                            #   리포트 생성
├── notebooks/                             # EDA · 프로토타이핑
└── AI_Lecture_Analysis_Report_Generator/  # ⛔ 제공 데이터 (git 미포함, 로컬 전용)
```

> ⚠️ `AI_Lecture_Analysis_Report_Generator/` 는 제공 데이터·기본 README·체크리스트를 담고 있으며
> **`.gitignore`에 의해 저장소에 포함되지 않습니다.** 로컬에서만 사용하세요.

---

## 🚀 시작하기

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 변수 설정 (.env.example 복사 후 키 입력)
cp .env.example .env
#   OPENAI_API_KEY=...  또는  ANTHROPIC_API_KEY=...

# 3. 실행 (예시)
python -m src.analyze --input "AI_Lecture_Analysis_Report_Generator/강의 스크립트"
```

> 제공 데이터는 저장소에 포함되지 않으므로, 로컬 `AI_Lecture_Analysis_Report_Generator/` 폴더에
> 원본 데이터를 직접 배치한 뒤 실행하세요.

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

## 👥 팀

| 이름 | 역할 |
|---|---|
| (작성 예정) | |
| (작성 예정) | |
| (작성 예정) | |
| (작성 예정) | |

---

## 🔒 데이터 보안 (필독)

제공 데이터는 **실제 강의 스크립트**를 포함하므로 아래를 반드시 준수합니다.

- 프로젝트 목적 외 사용 및 외부 공유 **금지**
- 개인 클라우드 · SNS 등 외부 업로드 **금지**
- **원본 데이터 GitHub 커밋 금지** → `.gitignore`로 `AI_Lecture_Analysis_Report_Generator/` 전체 제외 처리됨
- API 키는 `.env`에만 보관하며 커밋하지 않음
- 프로젝트 종료 후 모든 제공 데이터 **파기** 및 파기 확인서 제출

> 작업 전, 원본 데이터가 `git status`에 잡히지 않는지 반드시 확인하세요.
