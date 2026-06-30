# 📊 P4 리포트·대시보드 — pcr v3

> 담당: 박채린 (P4) · 브랜치: `pipeline/report/pcr/v3`
> v2 대비 변경: 하이브리드 analysis.jsonl 반영 · 평가방식 배지 · 메트릭 수치 표시 · 타임스탬프

---

## 📌 담당 범위

| 모듈 | 파일 | 상태 |
|---|---|---|
| 강의별 MD 리포트 | `src/report/build.py` | ✅ |
| 강의별 PDF 리포트 | `src/report/pdf.py` | ✅ v3 업데이트 |
| Streamlit 대시보드 | `src/report/dashboard.py` | ✅ v3 업데이트 |
| Streamlit 테마 설정 | `.streamlit/config.toml` | ✅ |

---

## 🆕 v3에서 달라진 점

> 배경: P2(pipeline/kys/v4)에서 하이브리드 평가 엔진이 도입됨.
> 항목별 `eval_type`(평가 방식), `metric`(수치 근거), `routing`(라우팅 메타)이
> analysis.jsonl에 추가되어 P4 리포트에도 반영이 필요해졌다.

### 대시보드 (`src/report/dashboard.py`)

| 항목 | 내용 |
|---|---|
| 평가방식 배지 | 각 항목에 평가 출처 배지 표시 — 지표(파랑) / 검색(노랑) / 전역(분홍) / 위치(초록) |
| 메트릭 수치 표시 | 지표형 항목에 수치 근거 pill 표시 (필러율·존댓말비율·이해확인·참여유도 빈도 등) |
| 타임스탬프 표시 | 항목 hover·클릭 시 헤더에 근거 청크 시간 범위 표시 (예: `09:12:00–09:17:30`) |
| v4 다중 지표 대응 | `top_filler`, `n`(cue 횟수) 등 v4 신규 metric 필드 자동 렌더링 |

### PDF (`src/report/pdf.py`)

| 항목 | 내용 |
|---|---|
| 평가방식 라벨 | 각 항목 옆에 `[지표]` / `[검색]` / `[전역]` / `[위치]` 텍스트 라벨 표시 |
| 메트릭 수치 강화 | `top_filler`, `n` 등 다중 지표값 표시 (예: `filler_rate=0.057 · 최다 '이렇게'`) |
| 타임스탬프 인용 | 근거 인용 옆에 청크 시간 범위 표시 (예: `(09:12:00-09:17:30)`) |

---

## 📐 평가방식 배지 상세

| eval_type | 배지 | 색상 | 설명 |
|---|---|---|---|
| `metric` | 지표 | 파랑 `#3b82f6` | 규칙 기반 수치 채점 (LLM 없음) |
| `local` | 검색 | 노랑 `#f59e0b` | 임베딩 검색 → LLM 판단 |
| `global` | 전역 | 분홍 `#ec4899` | 압축 전역뷰 → LLM 판단 |
| `positional` | 위치 | 초록 `#10b981` | 도입/종료부 위치 기반 → LLM 판단 |

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

```bash
# ①② 전처리 (강의 스크립트 → merged.jsonl)
python -m scripts.run_preprocess

# ③④⑤ 정제·청킹·태깅 (merged.jsonl → chunks.jsonl)
JAVA_HOME=/opt/homebrew/opt/openjdk@21 \
python -m scripts.run_refine_local --lecture 2026-02-03_오전

# ⑥ 분석 (chunks.jsonl → analysis.jsonl)  ← v4 하이브리드 엔진
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
- **좌측 패널**: C1~C5 카테고리 그룹 헤더 + 항목 리스트
  - 점수·판정 100자
  - **평가방식 배지** (v3 신규)
  - **메트릭 수치 pill** (v3 신규, 지표형 항목만)
- **우측 패널**: 강의 원문 전체
- **hover 인터랙션**:
  - 항목에 마우스를 올리면 근거 청크만 표시, 나머지는 흐리게(opacity 20%)
  - 근거 구절에 노란 형광펜(`<mark>`) 하이라이트 + 자동 스크롤
  - 헤더에 "근거 청크 N · 인용 N건 · **HH:MM:SS–HH:MM:SS**" 표시 (v3 신규)
  - hover 해제 400ms 후 원문 복원
- **click 인터랙션**:
  - 항목 클릭 시 파란 테두리로 고정(pin) — hover 해제해도 유지
  - 다시 클릭하면 고정 해제

### 탭 3 · 추이 분석 (📅)

- **종합 점수 추이**: 날짜별 강의력 점수 라인 차트
- **카테고리별 추이**: C1~C5 5선 라인 차트
- 단일 강의 시 안내 메시지, 다강의 데이터 시 자동 활성화

### 사이드바

- 데이터 파일 경로 입력 (scores / analysis / chunks)
- 강의 선택 드롭다운
- 전체 강의 수 / 평균 점수 지표
- **PDF 다운로드 버튼** — 선택 강의 리포트 즉시 저장

---

## 📁 입출력 스키마

### 입력 (v3 추가 필드)

| 파일 | 생성 주체 | v3에서 새로 사용하는 필드 |
|---|---|---|
| `analysis.jsonl` | P2 (engine.py) | `eval_type`, `metric.name`, `metric.value`, `metric.top_filler`, `metric.n` |
| `chunks.jsonl` | P1 (chunk_embed.py) | `start_time`, `end_time` (타임스탬프용) |
| `scores.json` | P3 (scoring.py) | 변경 없음 |

### 출력

| 파일 | 경로 | 설명 |
|---|---|---|
| MD 리포트 | `outputs/processed/reports/report_{lid}.md` | 강의별 텍스트 리포트 |
| PDF 리포트 | `outputs/processed/reports/report_{lid}.pdf` | 평가방식 라벨·타임스탬프 포함 |
| 대시보드 | `http://localhost:8501` | 배지·수치·타임스탬프 인터랙티브 뷰 |

---

## 📦 의존성

```
streamlit==1.45.1   # 대시보드
plotly==6.8.0       # 인터랙티브 차트
matplotlib          # PDF 레이더 차트 PNG 생성
reportlab           # PDF 생성
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

## ⏭️ 다음 단계 (v4 예정)

- [ ] LLM 기반 강의 종합 피드백 자동 생성 (개선 권고사항 텍스트)
- [ ] 부정 증거 항목 명시 시각화 (어떤 항목이 강의에서 관찰되지 않았는지)
- [ ] 평가 품질 지표 추가 (Weighted Kappa, Within-1 정확도, 카테고리별 MAE)
- [ ] 강의간 항목별 비교 기능
