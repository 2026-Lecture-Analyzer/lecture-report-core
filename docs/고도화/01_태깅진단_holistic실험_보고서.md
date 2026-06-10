# 평가 로직 고도화 — 태깅 진단 & Holistic 실험 보고서

- **작성일** 2026-06-10
- **대상 브랜치** `pipeline/kys/v3`
- **대상 강의** 2026-02-03 (오전·오후), 백엔드 Upstage `solar-pro2` · self-consistency 3
- **목적** 현재 RAG(항목별 retrieval) 평가의 부정확성 원인을 정량 진단하고, 전체원문 holistic 평가를 대조군으로 비교해 고도화 방향을 확정한다.

---

## 0. 요약 (TL;DR)

1. 현재 평가는 **"평가요소 하나당 강의 전체를 보는" 구조가 아니다.** 18항목 중 12항목(local·position)이 임베딩 검색으로 추린 **top-5 청크(강의의 ~10%)만** 보고 채점한다.
2. 그 검색 자체가 약하다 — **원문의 57%가 어떤 항목에도 안 잡히고(0태그)**, 유사도가 floor(0.45)에 겨우 걸치거나 미달한다(C3_definition 평균 0.359).
3. 전체원문 holistic 평가를 같은 강의에 돌린 결과, **RAG가 틀리던 지점이 정확히 교정**됐다. 대표적으로 (a) 검색이 놓쳐 "정의 없음 1점" 주던 항목을 holistic은 근거 인용과 함께 4점, (b) clean 텍스트에 속아 만점 주던 반복 메트릭의 오류가 드러남.
4. holistic은 **호출 6건(RAG 102건의 1/16)** 으로 더 싸다.
5. 결론 — **스코프 인지 하이브리드**로 전환: 인스턴스/구조 항목은 holistic, 빈도 항목은 **raw 텍스트 기반 메트릭(현재 버그 수정)**.

---

## 1. 현재 구조 — 항목별 retrieval(RAG)

태깅(`src/refine/tagging.py`)은 **항목 중심**으로 동작한다: 각 평가항목을 쿼리로 관련 청크 top-k(`TAG_TOP_K=5`)를 검색해 `eval_tags`를 부착. 분석(`src/analyze/engine.py`)은 항목 `eval_type`으로 4갈래 라우팅한다.

| 라우팅 | 항목 수 | 보는 범위 | 전체원문? |
|---|---|---|---|
| 🔵 metric | 2 (반복·속도) | clean_text **전체** (규칙) | ✅ 전수 |
| 🔴 global | 4 (완결성·일관성·순서·선행) | 균등 샘플 **8청크** (~17%) | △ 부분 |
| 🟢🟡 position | 3 (목표·복습·요약) | 위치게이트 + 태깅 **≤5** | ❌ peephole |
| 🟠 local | 9 (정의·비유·예시·실습·오류·상호작용 등) | 태깅 **≤5청크** (~10%) | ❌ peephole |

→ **18항목 중 12항목(local+position)이 강의의 ~10%만 보고 채점.** "평가요소 하나당 전체 원문" 이 구조적으로 불가능한 구간이 여기다. (RAG는 Solar 4k 컨텍스트 제약으로 강제된 설계였으나, 실제 refine 후 강의당 ~6~8k 토큰이라 더 이상 필요 없음 — §3.)

---

## 2. 태깅 정확도 정량 진단 (02-03 chunks.jsonl, 청크 94개)

### 2-1. 원문 57%가 사각지대
```
청크당 eval_tags 수:  0태그 54 · 1태그 22 · 2태그 10 · 3+ 8
→ 0태그 청크 54/94 = 57%  (local/position 12개 항목이 절대 못 보는 원문)
```
절반 넘는 청크가 어떤 항목에도 안 잡혀, metric(전수)·global(균등샘플) 외엔 평가에 미참여.

### 2-2. 검색 신호가 약함 (sim이 floor에 겨우 걸침)
- 대부분 항목 sim 평균 0.36~0.50, floor=0.45 → 관련/무관 변별폭 ~0.05.
- **C3_definition: sim 평균 0.359·최대 0.397 < floor 0.45** → dense 신호로는 0개, 순전히 키워드 cue로만 구제.
- 원인: 항목 description은 추상 평가기준 문장, 청크는 구어체 STT → 코사인이 원래 낮음.

### 2-3. Recall 누락 (시드 키워드는 본문에 있는데 태그 안 붙음)
| 항목 | 키워드 보유 청크 | 미태깅 | 누락률 |
|---|---|---|---|
| C2_objective (학습목표) | 16 | 15 | **94%** |
| C2_review (전날복습) | 4 | 4 | **100%** |
| C2_summary (마무리) | 3 | 2 | 67% |
| C2_emphasis (핵심강조) | 13 | 6 | 46% |
| C3_definition (개념정의) | 9 | 3 | 33% |

position 항목은 위치게이트(앞/뒤 20%) + top-5 cap이 겹쳐 본문 곳곳의 관련 발화를 통째로 놓친다.

### 2-4. 진단 결론 — 부정확함의 3대 원인
1. **Top-k=5 cap** (`TAG_TOP_K`/`ANALYZE_EVIDENCE_K`): 항목마다 강의의 ~10%만 입력.
2. **약한 dense 검색**: rubric문장 vs 구어체 → sim 0.4대, floor와 변별 거의 없음. 진짜 근거를 못 올리고 노이즈를 올림.
3. **57% 미태깅**: 절반 넘는 원문이 retrieval 평가에 미참여.

---

## 3. Holistic 실험 — 전체원문 1패스

### 3-1. 설계
- refine 산출(`clean.jsonl`)은 강의당 ~12,000자 ≈ **6~8k 토큰** (군더더기 제거로 22배 압축, 섹션마다 타임스탬프 보유) → **전체 전사가 한 프롬프트에 들어감.**
- 신규 실험 스크립트 `scripts/exp_holistic_eval.py` (기존 파이프라인 무수정, 별도 산출 `holistic_analysis.jsonl`):
  타임스탬프 부착 전체 전사 + 18항목 루브릭 → **한 호출로 18항목 일괄 채점**. 출력은 analysis.jsonl과 동일 스키마 → 같은 스코어러로 사과-대-사과 비교.
- self-consistency 3 (항목별 중앙값). 호출 = 강의당 1×SC.

### 3-2. 종합 점수
| | RAG (top-5 retrieval) | Holistic (전체원문) | 1주차 기준* |
|---|---|---|---|
| 오전 종합 | 52.0 | 50.2 | 42.2 |
| 오후 종합 | 47.6 | 44.4 | 31.1 |
| LLM 호출 | ~102건 | **6건 (1/16)** | — |

\* 1주차 기준은 다른 코드 버전 산출 → 항목 비교 대상 아님(둘 다 그보다 높음).

### 3-3. 항목별 비교 (RAG vs HOL)
```
▶ 2026-02-03_오전                         ▶ 2026-02-03_오후
item            type    RAG HOL  Δ        item            type    RAG HOL  Δ
C1_repetition   metric   5   2  -3 ▼      C1_repetition   metric   5   2  -3 ▼
C1_completeness global   4   4   0        C1_completeness global   5   4  -1 ▼
C1_consistency  global   5   5   0        C1_consistency  global   4   5  +1 ▲
C2_objective    intro    2   2   0        C2_objective    intro    1   1   0
C2_review       intro    1   2  +1 ▲      C2_review       intro    3   1  -2 ▼
C2_order        global   2   3  +1 ▲      C2_order        global   2   3  +1 ▲
C2_emphasis     local    4   3  -1 ▼      C2_emphasis     local    1   2  +1 ▲
C2_summary      outro    1   2  +1 ▲      C2_summary      outro    1   1   0
C3_definition   local    5   4  -1 ▼      C3_definition   local    1   4  +3 ▲
C3_analogy      local    2   3  +1 ▲      C3_analogy      local    2   1  -1 ▼
C3_prerequisite global   2   2   0        C3_prerequisite global   3   2  -1 ▼
C3_pace         metric   3   3   0        C3_pace         metric   3   3   0
C4_example      local    3   4  +1 ▲      C4_example      local    3   4  +1 ▲
C4_practice     local    2   2   0        C4_practice     local    3   3   0
C4_error        local    2   1  -1 ▼      C4_error        local    2   2   0
C5_check        local    1   2  +1 ▲      C5_check        local    2   1  -1 ▼
C5_engage       local    1   1   0        C5_engage       local    1   1   0
C5_answer       local    2   1  -1 ▼      C5_answer       local    1   1   0
```

---

## 4. 진단이 그대로 재현된 핵심 분기 (근거)

### ① C3_definition 오후: RAG 1점 → HOL 4점 — retrieval false-negative
- **RAG**: "모든 청크에서 핵심 개념을 정의하는 내용이 없음. 용어만 반복" → **1점.** 그러나 이 항목은 sim 0.359(floor 미달)로 **엉뚱한 청크만 검색**돼 정의 발화를 입력에서 아예 못 봤다.
- **HOL**: 전체를 읽고 실제 정의를 인용 → **4점.** 근거 예: *"테이블을 생성하면 데이터베이스는 폴더로, 테이블은 확장자 IBD 파일로…"*
- → 검색이 놓쳐 "없다"고 단정한 **가짜 0점.** §2 진단의 직접 증거.

### ② C1_repetition: RAG(규칙) 5점 → HOL 2점 (양 강의) — 메트릭 입력 오류
- **RAG 규칙** `filler_rate` = 0.047(오전)/0.067(오후) ≪ 임계 `FILLER_RATE_HIGH=0.15` → **5점.** 그러나 이 값은 **refine로 필러가 이미 제거된 `clean_text`에서 측정** → 항상 낮음 → 사실상 항상 만점. **측정 대상이 틀린 버그.**
- **HOL** 2점 ("동일 단어·연결어 과도 반복"). 사람이 만든 이상 리포트도 반복 항목 **2/5**. RAG 규칙만 동떨어짐.

### 패턴
- **RAG는 극단으로 튐**: retrieval 놓치면 1점(가짜 부재), 규칙이 clean에 속으면 5점.
- **HOL은 중간값으로 캘리브레이션**: 전체를 보니 1·5 남발이 줄고 사람 판단에 근접(특히 C1 카테고리: 사람=약함 / HOL=약함 / RAG=강함).

---

## 5. 한계 (정직한 기록)
1. HOL도 `clean_text`를 읽으므로 **원문 필러 카운트는 HOL도 못 한다.** 반복/속도 등 빈도 항목은 LLM이 아니라 **raw 텍스트 기반 메트릭**으로 정확히 재구현해야 한다.
2. 1주차 기준(42.2/31.1)은 **다른 코드 버전** 산출 → 항목별 정확도 비교 대상 아님.
3. HOL에 경미한 자기모순 1건(오후 반복 comment "과도하지 않음"인데 2점) — SC↑·structured output으로 완화 가능.
4. 본 비교는 **02-03 단일 강의** 기준. 일반화하려면 gold(사람 채점) 대조 필요(§6-1).

---

## 6. 고도화 로드맵 (확정 순서)

### 1순위 — Gold 검증
사람이 만든 **02-02 이상 리포트**를 정답으로 삼아, 같은 강의에 holistic·RAG를 돌려 **항목별 사람 점수와의 일치도(MAE/방향성)** 를 측정. "holistic이 정말 더 정확한가"를 데이터로 확정한다.

### 2순위 — 빈도 메트릭 raw 수정 (빠른 승리)
`filler_rate`·`pace` 계산을 `clean_text` → **`raw.jsonl`(원문)** 기준으로 교체. C1_repetition이 항상 5점 나오는 명백한 버그를 제거.

### 3순위 — 스코프 인지 하이브리드 본설계
analyze 라우팅을 다음으로 교체:
- **빈도/비율** (반복·필러·속도·이해확인 빈도) → raw 메트릭(2순위 결과)
- **인스턴스/품질** (정의·비유·예시·실습·오류대응) → holistic (전체원문)
- **전역/구조** (일관성·순서·목표·요약) → holistic 또는 메트릭 혼합

→ "평가요소가 원문을 한 번은 다 본다"가 구조적으로 보장되고, 호출 수도 감소.

---

## 7. Gold 검증 결과 (로드맵 1순위 실행 — 2026-06-10)

사람이 채점한 **02-02 강의 평가 리포트(하루 전체, 18항목)** 를 정답(gold)으로, 같은 강의에 RAG·holistic을 돌려 항목별 일치도를 측정. holistic은 **day 단위**(오전+오후 합쳐 1회) 채점 — gold가 하루 전체 관점이라 세션 평균이 도입/요약 항목을 부당히 깎는 문제를 제거(`exp_holistic_eval --by-date`). RAG는 세션 단위라 day 평균. 산출 `outputs/processed/_gold_0202/`.

### 7-1. 종합 일치도
| | MAE (↓ 정확) | 방향일치(±1) | 편향 |
|---|---|---|---|
| RAG | 1.86 | 6/18 (33%) | **-1.03** (사람보다 박함) |
| **Holistic (day)** | **1.00** | **15/18 (83%)** | **+0.11** (거의 무편향) |

→ **holistic이 사람 gold에 압도적으로 근접.** RAG는 -1점 체계적 과소평가.

### 7-2. 카테고리별 (GOLD / RAG / HOL)
| 카테고리 | GOLD | RAG | HOL | 비고 |
|---|---|---|---|---|
| C1 언어 표현 | 7 | 14.5 | 13.0 | **둘 다 과대** ← 핵심 결함 |
| C2 도입/구조 | 20 | 9.0 | **19.0** | holistic 완벽, RAG는 retrieval로 목표·복습 놓침 |
| C3 개념 명확성 | 15 | 11.0 | 16.0 | holistic ±1 |
| C4 예시/실습 | 12 | 7.0 | 11.0 | holistic ±1 |
| C5 상호작용 | 9 | 3.0 | 6.0 | 단일화자 한계로 둘 다 과소 |

### 7-3. 핵심 통찰 — C1은 holistic으로도 안 된다 (원인 규명)
C1 항목(반복·완결성·일관성)이 잡아야 할 결함(필러·끊긴 문장·반말 혼용)을 **refine가 `clean_text`에서 이미 제거**한다. 그래서 정제본을 읽는 한 메트릭이든 holistic이든 "깨끗함=만점"으로 속는다.
- 증거: C1_consistency gold **2**(사람은 반말 혼용 감지) vs RAG **5**·HOL **5**. C1_repetition gold 2 vs RAG 5(메트릭 버그)·HOL 3.
- → **C1 카테고리 전체를 `raw.jsonl`(원문) 기준으로 평가**해야 한다. 로드맵 2순위(메트릭 raw 수정)를 **C1 3항목 전체로 확장**.

### 7-4. 결론
- **holistic = C2/C3/C4 에서 사람 수준**(MAE ~0.5). retrieval 가짜-부재 완전 해소.
- **C1 = raw 필요**(정제가 신호를 지움). **C5 = 데이터 한계**(단일화자).
- 고도화 방향 재확인: **C1→raw 신호 · C2~C4→holistic · C5→데이터/프롬프트 보정.**

---

## 8. 로드맵 2순위 실행 — C1 메트릭 raw 수정 (2026-06-11)

§7 gold 검증에서 드러난 C1 과대평가 원인을 실측으로 정밀 규명 후 수정.

### 8-1. 실측 원인 (02-02 raw vs clean)
| 신호 | 입력 | 값 | gold | 진단 |
|---|---|---|---|---|
| honorific_ratio | clean(기존) | **1.0** → 5점 | 2 | 정제가 전부 존댓말로 정규화(300:0) |
| honorific_ratio | **raw** | **0.532** → 2점 | 2 | raw는 525:462 반말 혼용 그대로 |
| filler_rate | raw(기존) | 0.057 → 5점 | 2 | rate는 낮으나 '이렇게' 361회(1.76%) 단일 폭증 |
| incomplete_ratio | raw 블록(기존) | 0.083 → 5점 | 3 | merged 블록이 끊김을 뭉갬 |

### 8-2. 수정 내용 (`src/analyze/metrics.py`, `src/config.py`)
1. **honorific_ratio → raw(merged.text) 기준.** clean_text 의존 제거. (rule + global_prompt LLM 앵커 동시 교정)
2. **지배 필러 신호 추가** (`max_filler_rate`/`top_filler`): 단일 필러 비중 > `FILLER_DOMINANT_HIGH(0.015)` 면 '특정 표현 과반복' 감점.
3. **C1_repetition 채점 = 총 필러율 OR 지배 필러** 둘 중 하나만 넘어도 2점.
4. `FILLER_RATE_HIGH` 0.15 → **0.06** (비현실적 임계 보정).

### 8-3. 효과 (RAG, 02-02, end-to-end)
| C1 항목 | 수정 전 | 수정 후 | gold |
|---|---|---|---|
| C1_repetition (metric) | 5 | **2** | 2 ✓ |
| C1_consistency (global) | 5 | **2** | 2 ✓ |
| C1_completeness (global) | 4.5 | 4.5 | 3 (잔존) |
| **C1 카테고리 합** | 14.5 | **8.5** | 7 |
| **RAG 전체 MAE** | 1.86 | **1.47** | — |

C1 과대평가(+7.5 → +1.5) 거의 해소. **남은 것: C1_completeness** — merged 블록이 끊김을 뭉개 과대평가. raw 발화(pre-merge) 단위 미완결률 측정이 필요(후속).

> 주의: 본 보정은 gold 단일 강의(02-02) 기준. 필러 임계는 §2차 다강의 EDA 로 재확인 필요(코드 주석에 명시).

---

## 9. 로드맵 3순위 — 스코프 인지 하이브리드 (2026-06-11)

gold 가 증명한 라우팅으로 평가 엔진을 재구성. 설계: **holistic 로 18항목 채점 후, 결정적 4항목만 raw 메트릭으로 덮어쓰기**(reuse 최대, 출력 스키마 동일 → 스코어러·리포트·대시보드 그대로). 신규 러너 `scripts/run_hybrid_eval.py`.

| 입력 방식 | 항목 | 근거 |
|---|---|---|
| **raw 메트릭**(결정적, LLM 없음) | C1_repetition · C1_consistency · C1_completeness · C3_pace | §8 — 정제본은 결함 지움 |
| **holistic**(전체원문 1패스 LLM) | 나머지 14 (C2 구조·C3 개념·C4 실습·C5 상호작용) | §7 — 사람 수준 |

### 9-1. gold 일치도 (02-02) — 3방식 비교
| 방식 | MAE (↓) | 방향일치(±1) | 편향 | LLM 호출 |
|---|---|---|---|---|
| RAG (top-5 retrieval) | 1.47 | 8/18 (44%) | -1.31 | ~102 |
| Holistic (전체원문) | 1.00 | 15/18 (83%) | +0.11 | 6 |
| **하이브리드** | **0.89** | 13/18 (72%) | -0.44 | 6 |

→ **하이브리드가 사람 gold에 가장 근접(MAE 0.89).** C1=메트릭(정확) + C2~C4=holistic(사람 수준) 조합 효과.

### 9-2. 잔존 오차 (전부 기지 한계)
| 항목 | HYB | gold | 원인 | 후속 |
|---|---|---|---|---|
| C1_completeness | 5 | 3 | merged 블록이 끊김 뭉갬 | raw 발화(pre-merge) 미완결률 |
| C4_error | 2 | 4 | holistic 박함·SC 변동 | 프롬프트 가이드 보정 |
| C5_check·answer | 1 | 3 | 단일화자 데이터 한계 | 화자분리/프롬프트 재해석 |

### 9-3. 상태
하이브리드 러너 검증 완료 → **새 평가 엔진의 후보.** 출력이 analysis.jsonl 동일 스키마라 `run_score_local`·`run_report_local`·대시보드에 그대로 연결 가능. 본격 승격(엔진 기본 경로 교체) 시 RAG 경로는 비교용으로 보존 권장.

---

## 부록 — 재현 방법
```bash
# 태깅 진단(읽기전용, LLM 호출 없음)
python scripts/inspect_tagging_quality.py --chunks outputs/processed/chunks.jsonl

# holistic 실험 (.env LLM_BACKEND 백엔드 따름)
python -m scripts.exp_holistic_eval --self-consistency 3        # → holistic_analysis.jsonl
python -m scripts.run_analyze_local --self-consistency 3 --fresh # RAG 완주 → analysis.jsonl
python -c "import scripts.exp_holistic_eval as ex; from src import config; \
  ex._compare(config.PROCESSED_DIR/'analysis.jsonl', config.PROCESSED_DIR/'holistic_analysis.jsonl')"

# Gold 검증 (02-02, 사람 채점 대조) — §7
D=outputs/processed/_gold_0202
python -m scripts.run_refine_local --file 2026-02-02_kdt-backendj-21th.txt --out-dir $D --fresh
python -m scripts.run_analyze_local --chunks $D/chunks.jsonl --out $D/analysis.jsonl --merged outputs/processed/merged.jsonl --self-consistency 3 --fresh
python -m scripts.exp_holistic_eval --clean $D/clean.jsonl --out $D/holistic_analysis.jsonl --by-date --self-consistency 3
python -m scripts.exp_gold_compare --dir $D
```

관련 코드: `src/refine/tagging.py`(태깅) · `src/analyze/engine.py`(라우팅) · `src/config.py`(`TAG_*`/`FILLER_RATE_HIGH`) · `scripts/exp_holistic_eval.py`(holistic 실험) · `scripts/exp_gold_compare.py`(gold 대조, 정답 점수 내장).
