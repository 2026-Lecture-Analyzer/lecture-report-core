# 📊 P4 리포트·대시보드 — pcr v1

> 담당: 박채린 (P4) · 브랜치: `pipeline/report/pcr/v1`
> 입력: `scores.json` + `analysis.jsonl` + `chunks.jsonl` → MD 리포트 / PDF / Streamlit 대시보드

---

## 📌 담당 범위

| 모듈 | 파일 | 상태 |
|---|---|---|
| 강의별 MD 리포트 | `src/report/build.py` | ✅ |
| 강의별 PDF 리포트 | `src/report/pdf.py` | ✅ |
| Streamlit 대시보드 | `src/report/dashboard.py` | ✅ |
| Streamlit 테마 설정 | `.streamlit/config.toml` | ✅ |

---

## 🚀 실행 방법

### 환경 설정

```bash
# Python 3.13 설치 (Homebrew)
brew install python@3.13

# 가상환경 생성 및 의존성 설치
/opt/homebrew/bin/python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# KoNLPy 사용 시 Java 필요 (정제·청킹 단계)
brew install openjdk@21
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
```

### 파이프라인 전체 실행 (로컬)

> 앞 단계 산출물이 있어야 뒤 단계를 실행할 수 있습니다.

```bash
# ①② 전처리 (강의 스크립트 → merged.jsonl)
python -m scripts.run_preprocess

# ③④⑤ 정제·청킹·태깅 (merged.jsonl → chunks.jsonl)
#   비용 안전장치: --lecture 로 한 강의만, --dry-run 으로 계획만 확인
JAVA_HOME=/opt/homebrew/opt/openjdk@21 \
python -m scripts.run_refine_local --lecture 2026-02-03_오전

# ⑥ 분석 (chunks.jsonl → analysis.jsonl)
JAVA_HOME=/opt/homebrew/opt/openjdk@21 \
python -m scripts.run_analyze_local --lecture 2026-02-03_오전

# ⑦ 스코어링 (analysis.jsonl → scores.json)
python -m scripts.run_score_local

# ⑧ MD + PDF 리포트 생성
python -m scripts.run_report_local --pdf
#   → outputs/processed/reports/report_{lid}.md
#   → outputs/processed/reports/report_{lid}.pdf
```

### 대시보드 실행

```bash
.venv/bin/streamlit run src/report/dashboard.py
# → http://localhost:8501
```

---

## 📊 대시보드 구성

### 탭 1 · 개요 (📈)

| 구성 요소 | 설명 |
|---|---|
| 핵심 지표 4개 | 종합점수 / 최고·최저 카테고리 / 부정 증거 항목 수 |
| 레이더 차트 | 5개 카테고리(C1~C5) 점수 시각화 |
| 막대 차트 | 카테고리별 점수 비교 |
| 강점 / 개선점 | 항목 norm 기준 상·하위 3항목 |

### 탭 2 · 항목별 상세 + 원문 (📋)

- **좌측 패널**: 18개 평가항목 리스트 (카테고리 색 구분, 항목명, 점수)
- **우측 패널**: 강의 원문 전체 (chunks.jsonl 청크 순서대로)
- **hover 인터랙션**:
  - 항목에 마우스를 올리면 해당 항목의 근거 청크만 표시, 나머지는 흐리게(opacity 20%)
  - 근거 구절에 노란 형광펜(`<mark>`) 하이라이트
  - 우측 패널이 해당 청크로 자동 스크롤
  - 헤더에 "근거 청크 N · 인용 N건" 표시
  - hover 해제 400ms 후 원문 복원

### 탭 3 · 추이 분석 (📅)

- **종합 점수 추이**: 날짜별 강의력 점수 라인 차트
- **카테고리별 추이**: C1~C5 5선 라인 차트
- 단일 강의 시 안내 메시지, **다강의 데이터가 들어오면 자동으로 차트 활성화**
- 하단 데이터 테이블 제공

---

## 📁 입출력 스키마

### 입력

| 파일 | 생성 주체 | 주요 필드 |
|---|---|---|
| `scores.json` | P3 (scoring.py) | `lectures.{lid}.total_score`, `category_scores`, `items[].norm` |
| `analysis.jsonl` | P2 (engine.py) | `item_key`, `score`, `verdict`, `evidence[].quote`, `comment` |
| `chunks.jsonl` | P1 (chunk_embed.py) | `chunk_id`, `lecture_id`, `clean_text`, `eval_tags` |

### 출력

| 파일 | 경로 | 설명 |
|---|---|---|
| MD 리포트 | `outputs/processed/reports/report_{lid}.md` | 강의별 텍스트 리포트 |
| PDF 리포트 | `outputs/processed/reports/report_{lid}.pdf` | 한글 TTF 기반 PDF |
| 대시보드 | `http://localhost:8501` | Streamlit 인터랙티브 뷰 |

---

## 🐛 수정한 버그

| 파일 | 내용 |
|---|---|
| `scripts/run_refine_local.py` | manifest 저장 시 `config.TAG_SIM_THRESHOLD` → `config.TAG_RETRIEVE_FLOOR` 오탈자 수정 |
| `.gitignore` | 심볼릭 링크(`AI_Lecture_Analysis_Report_Generator`)가 gitignore에서 누락되던 문제 수정 (슬래시 없는 패턴 추가) |

---

## 📦 추가된 의존성

```
streamlit==1.45.1   # 대시보드
plotly==6.8.0       # 인터랙티브 차트 (레이더·막대·라인)
```

> `pip install -r requirements.txt` 로 일괄 설치됩니다.

---

## 🔧 설정 파일

### `.streamlit/config.toml`

라이트 테마 고정 — 팀원 시스템의 다크모드 설정과 무관하게 일관된 UI 보장.

```toml
[theme]
base = "light"
primaryColor = "#6366f1"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f8fafc"
textColor = "#1e293b"
font = "sans serif"
```

---

## ⏭️ 다음 단계 (v2 예정)

- [ ] PDF 레이아웃 고도화 — 카테고리 레이더 차트 삽입
- [ ] 강사 비교 리포트 — 15강의 전체 배치 처리 후 강사별 집계 MD/PDF
- [ ] 추이 분석 — 15강의 API 실행 완료 후 실데이터 검증
