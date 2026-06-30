# 📊 P4 리포트·대시보드 — pcr v2

> 담당: 박채린 (P4) · 브랜치: `pipeline/report/pcr/v2`
> v1 대비 변경: PDF 레이더 차트 · 대시보드 UX 고도화 · 버그 수정

---

## 📌 담당 범위

| 모듈 | 파일 | 상태 |
|---|---|---|
| 강의별 MD 리포트 | `src/report/build.py` | ✅ |
| 강의별 PDF 리포트 | `src/report/pdf.py` | ✅ v2 신규 |
| Streamlit 대시보드 | `src/report/dashboard.py` | ✅ v2 신규 |
| Streamlit 테마 설정 | `.streamlit/config.toml` | ✅ |

---

## 🆕 v2에서 달라진 점

### PDF (`src/report/pdf.py`)

| 항목 | 내용 |
|---|---|
| 레이더 차트 삽입 | matplotlib으로 5개 카테고리 레이더 차트 PNG 생성 후 PDF에 삽입 |
| 한글 폰트 적용 | 차트 레이블에 시스템 한글 TTF(AppleGothic/NanumGothic) 자동 탐색 적용 |

### 대시보드 (`src/report/dashboard.py`)

| 항목 | 내용 |
|---|---|
| Deprecation 수정 | `st.components.v1.html` → `st.iframe` (base64 data URL) |
| Deprecation 수정 | `use_container_width=True` → `width='stretch'` |
| 탭2 카테고리 그룹 헤더 | 좌측 항목 패널에 C1~C5 카테고리 구분 헤더 추가 |
| verdict 표시 확장 | 판정 문구 40자 → 100자 |
| 클릭 고정(pin) | 항목 클릭 시 형광펜 고정, 다시 클릭하면 해제 |
| PDF 다운로드 버튼 | 사이드바에서 현재 강의 PDF 즉시 다운로드 |
| 18항목 요약 테이블 | 탭2 상단 접이식 테이블 (카테고리·항목·중요도·점수·판정) |
| 헤더 렌더링 수정 | 원문 헤더 `&nbsp;` 엔티티 깨짐 수정 (`textContent` → `innerHTML`) |

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
> 다강의 실행 시 강의별로 순서대로 실행하면 chunk_id 정합성이 유지됩니다.

```bash
# ①② 전처리 (강의 스크립트 → merged.jsonl)
python -m scripts.run_preprocess

# ③④⑤ 정제·청킹·태깅 (merged.jsonl → chunks.jsonl)
#   주의: 강의별로 순서대로 실행해야 chunk_id가 분석과 일치
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

- **상단**: 전체 18항목 요약 테이블 (접이식 expander)
- **좌측 패널**: C1~C5 카테고리 그룹 헤더 + 항목 리스트 (점수·판정 100자)
- **우측 패널**: 강의 원문 전체
- **hover 인터랙션**:
  - 항목에 마우스를 올리면 근거 청크만 표시, 나머지는 흐리게(opacity 20%)
  - 근거 구절에 노란 형광펜(`<mark>`) 하이라이트 + 자동 스크롤
  - 헤더에 "근거 청크 N · 인용 N건" 표시
  - hover 해제 400ms 후 원문 복원
- **click 인터랙션**:
  - 항목 클릭 시 파란 테두리로 고정(pin) — hover 해제해도 유지
  - 다시 클릭하면 고정 해제

### 탭 3 · 추이 분석 (📅)

- **종합 점수 추이**: 날짜별 강의력 점수 라인 차트
- **카테고리별 추이**: C1~C5 5선 라인 차트
- 단일 강의 시 안내 메시지, **다강의 데이터 시 자동 활성화**
- 하단 데이터 테이블 제공

### 사이드바

- 데이터 파일 경로 입력 (scores / analysis / chunks)
- 강의 선택 드롭다운
- 전체 강의 수 / 평균 점수 지표
- **PDF 다운로드 버튼** — 선택 강의 리포트 즉시 저장

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
| PDF 리포트 | `outputs/processed/reports/report_{lid}.pdf` | 레이더 차트 포함 한글 TTF 기반 PDF |
| 대시보드 | `http://localhost:8501` | Streamlit 인터랙티브 뷰 |

---

## 🐛 수정한 버그

| 파일 | 내용 |
|---|---|
| `src/analyze/engine.py` | LLM 응답이 list일 때 `AttributeError: 'list' object has no attribute 'get'` 수정 |
| `src/report/dashboard.py` | 원문 헤더 `&nbsp;` 엔티티가 문자 그대로 출력되던 문제 수정 (`textContent` → `innerHTML`) |

---

## 📦 의존성

```
streamlit==1.45.1   # 대시보드
plotly==6.8.0       # 인터랙티브 차트
matplotlib          # PDF 레이더 차트 PNG 생성 (requirements.txt 포함)
```

> `pip install -r requirements.txt` 로 일괄 설치됩니다.

---

## ⚠️ 다강의 실행 시 주의사항

`chunks.jsonl`의 `chunk_id`는 전체 강의에 걸쳐 순차 부여됩니다.
분석(`run_analyze_local`) 실행 이후 다른 강의를 청킹하면 chunk_id가 바뀌어
형광펜 하이라이트가 동작하지 않을 수 있습니다.

**권장 순서**: 모든 강의를 `run_refine_local` → `run_analyze_local` 순으로 처리한 뒤
`run_score_local` → `run_report_local` 을 마지막에 실행하세요.

---

## ⏭️ 다음 단계 (v3 예정)

- [ ] 강사 비교 리포트 — 15강의 전체 배치 처리 후 강사별 집계 MD/PDF
- [ ] 추이 분석 — 15강의 API 실행 완료 후 실데이터 검증
- [ ] chunk_id 강의 내 독립 부여 방식으로 개선 (다강의 실행 순서 의존성 제거)
