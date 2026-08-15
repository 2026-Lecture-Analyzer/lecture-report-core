# 📊 P4 리포트·대시보드 — pcr v4

> 담당: 박채린 (P4) · 브랜치: `deploy/pcr`
> v3 대비 변경: 프롬프트 채점 가이드 고도화(C3·C5) · 메트릭 cross-강사 캘리브레이션 · PDF 하이라이트 · SaaS 멀티테넌트 서비스 · 배포 인프라 · 성능평가 스크립트

---

## 📌 담당 범위

| 모듈 | 파일 | 상태 |
|---|---|---|
| 강의별 MD 리포트 | `src/report/build.py` | ✅ |
| 강의별 PDF 리포트 | `src/report/pdf.py` | ✅ v4 유지 |
| Streamlit 대시보드 | `src/report/dashboard.py` | ✅ v4 업데이트 |
| PDF 하이라이트 HTML | `src/report/highlight_html.py` | ✅ v4 신규 |
| 하이라이트 컴포넌트 | `src/report/highlight_component.py` | ✅ v4 신규 |
| 분석 프롬프트 (C3·C5) | `src/analyze/prompts.py` | ✅ v4 고도화 |
| 메트릭 캘리브레이션 | `src/analyze/metrics.py` | ✅ v4 업데이트 |
| SaaS 서비스 | `service/` | ✅ v4 신규 |
| 배포 인프라 | `deploy/`, `.github/workflows/` | ✅ v4 신규 |
| 성능평가 스크립트 | `scripts/run_mae_eval.py`, `scripts/gen_mae_pdf.py` | ✅ v4 신규 |

---

## 🆕 v4에서 달라진 점

### 1. 프롬프트 채점 가이드 고도화 (C3·C5 담당 항목)

**C3 — 개념 설명 명확성 (6개 항목)**

| 변경 | 내용 |
|---|---|
| ITEM_GUIDES 정밀화 | `C3_analogy`, `C3_code_explanation`, `C3_term_explanation` 등 6개 항목 채점 기준 구체화 |
| 항목 경계 명시 | `analogy` ↔ `code_explanation`, `prerequisite` ↔ `concept_connection` 혼동 방지 가이드 추가 |
| 근거 인용 기준 보강 | 점수 임계값·항목 경계 예시 추가 |
| C3_analogy SQL 예시 | SQL JOIN 등 실제 강의 도메인 기반 예시 명시 |

**C5 — 예시·실습 적절성**

| 변경 | 내용 |
|---|---|
| C5_example | 구체적 수치·기업 사례·실생활 비교도 실무 예시로 인정 → MAE 0.75 → **0.22** |
| C5_practice | 강사 시연·워밍업·연습·함수 적용도 '실습 연계 있음'으로 인정, 점수 밴드 명시 |

### 2. 메트릭 cross-강사 캘리브레이션

gold 9강의(KDT 백엔드 + 클라우드 강사) 기준 MAE **0.81 → 0.59**, 방향일치율 **80% → 93%**.

| 항목 | 변경 내용 |
|---|---|
| C4_pace | 범위 내여도 '우수(5)' 단정 불가 → 5→4(양호)로 캡. 클라우드 강의 과대평가 교정 (MAE 1.9→0.9) |
| C1_completeness | 미완결 낮아도 5→4 캡. 클라우드 과대평가 교정 (MAE 1.6→0.6) |
| C2_review | holistic LLM(MAE 2.1) → 복습 cue 카운팅 메트릭으로 전환 (MAE **0.22**). `config.REVIEW_CUES` 관리 |

### 3. PDF 하이라이트 개선

- `src/report/highlight_html.py` 신규: 형광펜 부분일치 — 잘린 `…` 인용도 최장 접두 일치로 표시
- `src/report/dashboard.py`: 형광펜 매칭 로직 개선

### 4. 근거 retrieval 분리 + 프롬프트 구조화

- holistic 점수는 유지, 근거(evidence)는 항목별 태깅(`eval_tags`) top-k 로 교체
- cue 확정 태그만 사용해 휴식 공지·UI 안내 등 오탐 제거
- ITEM_GUIDES 카테고리 섹션/담당자별로 구조화 (C3: 박채린, C4: 정찬희, C5: 김예슬, C2: 이지선)

### 5. SaaS 멀티테넌트 서비스 (`service/`)

로컬 전용이던 대시보드를 다중 사용자가 쓸 수 있도록 서비스 레이어 구축.

| 모듈 | 내용 |
|---|---|
| `auth.py` | Google OIDC 로그인 |
| `workspace.py` | 워크스페이스 관리 (초대 링크 기반) |
| `keys.py` | BYO(Bring Your Own) API 키 관리 |
| `pipeline.py` | 워크스페이스별 파이프라인 실행 |
| `report_view.py` | 보고서 뷰 서빙 |
| `store.py` | 데이터 저장소 |
| `migrate.py` | DB 마이그레이션 |

### 6. 배포 인프라

| 구성 요소 | 내용 |
|---|---|
| `deploy/Dockerfile` | 앱 컨테이너 이미지 |
| `deploy/docker-compose.yml` | app + Caddy(자동 TLS) 구성 |
| `deploy/Caddyfile` | Caddy 리버스 프록시 설정 |
| `.github/workflows/deploy.yml` | GitHub Actions CI/CD (push → 자동 배포) |
| `.streamlit/config.toml` | Streamlit 테마 설정 |

### 7. 성능평가 스크립트

| 스크립트 | 내용 |
|---|---|
| `scripts/run_mae_eval.py` | gold vs 파이프라인 예측 MAE 계산. 박채린·정찬희 gold 합산 지원 |
| `scripts/gen_mae_pdf.py` | MAE 결과를 카테고리별 차트 포함 PDF로 출력 |
| `fix(mae_eval)` | gold 항목 score가 null 또는 na인 경우 스킵 처리 |

---

## 🚀 실행 방법

### 환경 설정

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 파이프라인 전체 실행 (한방)

```bash
bash scripts/run_all.sh
```

### 단계별 실행

```bash
# ①② 전처리
python -m scripts.run_preprocess

# ③④⑤ 정제·청킹·태깅
JAVA_HOME=/opt/homebrew/opt/openjdk@21 \
python -m scripts.run_refine_local --lecture 2026-02-03_오전

# ⑥ 분석 (하이브리드 엔진)
python -m scripts.run_analyze_local --lecture 2026-02-03_오전

# ⑦ 스코어링
python -m scripts.run_score_local

# ⑧ MD + PDF 리포트
python -m scripts.run_report_local --pdf
```

### 대시보드 실행

```bash
.venv/bin/streamlit run src/report/dashboard.py
# → http://localhost:8501
```

### SaaS 서비스 실행 (Docker)

```bash
cd deploy
docker compose up -d
# → https://<도메인> (Caddy 자동 TLS)
```

### 성능평가

```bash
# MAE 계산
python -m scripts.run_mae_eval

# MAE 결과 PDF 출력
python -m scripts.gen_mae_pdf
# → outputs/gold_eval/성능평가_합산_박채린_정찬희.pdf
```

---

## 📊 성능 개선 요약

| 항목 | v3 MAE | v4 MAE | 개선 |
|---|---|---|---|
| 전체 (9강의 gold) | 0.81 | **0.59** | ↓ 27% |
| 방향일치율 | 80% | **93%** | ↑ 13%p |
| C5_example | 0.75 | **0.22** | ↓ 71% |
| C2_review | 2.1 | **0.22** | ↓ 90% |
| C4_pace (클라우드) | 1.9 | **0.9** | ↓ 53% |
| C1_completeness (클라우드) | 1.6 | **0.6** | ↓ 63% |

---

## 📁 입출력 스키마

### 입력

| 파일 | 생성 주체 | 사용 필드 |
|---|---|---|
| `analysis.jsonl` | P2 (engine.py) | `eval_type`, `metric.*`, `routing`, `eval_tags` |
| `chunks.jsonl` | P1 (chunk_embed.py) | `start_time`, `end_time` |
| `scores.json` | P3 (scoring.py) | 변경 없음 |

### 출력

| 파일 | 경로 | 설명 |
|---|---|---|
| MD 리포트 | `outputs/processed/reports/report_{lid}.md` | 강의별 텍스트 리포트 |
| PDF 리포트 | `outputs/processed/reports/report_{lid}.pdf` | 평가방식 라벨·타임스탬프 포함 |
| MAE 결과 PDF | `outputs/gold_eval/성능평가_합산_박채린_정찬희.pdf` | 카테고리별 MAE 차트 |
| 대시보드 | `http://localhost:8501` | 인터랙티브 뷰 |

---

## 📦 의존성

```
streamlit==1.58.0   # 대시보드 (pandas 3 충돌 해소 버전)
plotly==6.8.0       # 인터랙티브 차트
matplotlib          # PDF 레이더 차트 PNG 생성
reportlab           # PDF 생성
```

---

## ⏭️ 다음 단계 (v5 예정)

- [ ] LLM 기반 강의 종합 피드백 자동 생성 (개선 권고사항 텍스트)
- [ ] 부정 증거 항목 명시 시각화
- [ ] 강의간 항목별 비교 기능
- [ ] SaaS 서비스 안정화 및 모니터링
