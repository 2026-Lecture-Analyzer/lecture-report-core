# P2 Analyze 업데이트 기록 — 새 강의 품질 기준 반영 및 Hybrid 분석 엔진 전환

## 1. 작업 배경

기존 분석 엔진은 기존 `강의 품질 기준.pdf` 기준의 18개 평가 항목을 기반으로 동작했다.
이후 `new_강의 품질 기준.pdf` 기준으로 평가 항목과 카테고리 구성이 변경되었기 때문에, 분석 엔진의 기준 데이터, 라우팅 방식, metric 처리, prompt guide, 실행 진입점, 데이터 계약 문서를 새 기준에 맞게 수정했다.

또한 기존 RAG 기반 평가 방식은 태깅된 일부 청크에 의존하기 때문에, 태깅이 누락되거나 검색 후보가 부족한 경우 실제 강의 내용에 근거가 있어도 평가가 불안정해질 수 있었다. 이를 보완하기 위해 기본 분석 경로를 Hybrid 방식으로 변경했다.

현재 기본 분석 방식은 다음과 같다.

```text
Hybrid 분석 = 전체 원문 기반 holistic LLM 평가 14항목 + raw metric 기반 결정적 평가 4항목
```

기존 RAG 기반 분석은 삭제하지 않고 `--legacy` 옵션으로 보존했다.

---

## 2. 변경 파일

### 수정 파일

```text
src/analyze/checklist.py
src/analyze/prompts.py
src/analyze/metrics.py
src/analyze/engine.py
scripts/run_hybrid_eval.py
scripts/run_analyze_local.py
docs/SCHEMA.md
```

### 신규 파일

```text
src/analyze/hybrid.py
```

---

## 3. 새 강의 품질 기준 반영

`checklist.py`를 `new_강의 품질 기준.pdf` 기준으로 교체했다.

### 새 평가 카테고리

| 카테고리 |        이름 | 항목 수 |
| ---- | --------: | ---: |
| C1   |  언어 표현 품질 |    3 |
| C2   |     강의 구조 |    5 |
| C3   | 개념 설명 명확성 |    6 |
| C4   |     진행 방식 |    2 |
| C5   |   실습 및 적용 |    2 |

총 18개 평가 항목 구조는 유지했다.

---

## 4. 삭제된 기존 항목

새 기준에서 제거된 항목은 기본 Hybrid 평가 경로에서 제외했다.

```text
C4_error    오류 대응
C5_check    이해 확인 질문
C5_engage   참여 유도
C5_answer   질문 응답 충분성
```

위 항목들은 새 기준에 포함되지 않으므로 기본 `analysis.jsonl` 산출물에 포함되지 않는다.

---

## 5. 신규 추가 항목

새 기준에서 추가된 항목은 다음과 같다.

```text
C3_term_explanation     용어 설명 충분성
C3_concept_connection   개념 간 연결성
C3_code_explanation     코드 설명 충실성
C4_transition           학습 전환 안내
```

---

## 6. 카테고리 이동 항목

기존 항목 중 일부는 새 기준의 카테고리 구조에 맞게 key를 변경했다.

```text
C3_pace      → C4_pace
C4_example   → C5_example
C4_practice  → C5_practice
```

---

## 7. Hybrid 라우팅 구조

새 기준 기준으로 Hybrid 라우팅을 재정의했다.

### Raw Metric 평가 항목

다음 4개 항목은 LLM이 아니라 raw/merged 데이터에서 계산한 규칙 기반 metric으로 평가한다.

```text
C1_repetition
C1_completeness
C1_consistency
C4_pace
```

### Holistic Full Context 평가 항목

나머지 14개 항목은 강의 전체 원문을 기반으로 LLM이 holistic 평가한다.

```text
C2_objective
C2_review
C2_structure
C2_emphasis
C2_summary
C3_definition
C3_term_explanation
C3_analogy
C3_prerequisite
C3_concept_connection
C3_code_explanation
C4_transition
C5_example
C5_practice
```

### 라우팅 방식 요약

```text
raw_metric           : 규칙 기반 지표 평가
holistic_fullcontext : 전체 원문 기반 LLM 평가
```

---

## 8. `src/analyze/hybrid.py` 신설

기존 `scripts/run_hybrid_eval.py`에 있던 Hybrid 핵심 로직을 `src/analyze/hybrid.py`로 분리했다.

### 역할

`src/analyze/hybrid.py`

```text
- 공통 Hybrid 분석 코어
- run_hybrid_analysis() 제공
- holistic 14항목 평가 실행
- raw metric 4항목 덮어쓰기
- routing.method 기록
```

`scripts/run_hybrid_eval.py`

```text
- 실험용 wrapper
- gold 비교 및 빠른 테스트용
```

`scripts/run_analyze_local.py`

```text
- 정식 분석 실행 진입점
- 기본 실행은 Hybrid
- --legacy 옵션으로 기존 RAG 경로 보존
```

---

## 9. `run_analyze_local.py` 기본 실행 경로 변경

기존에는 `run_analyze_local.py`가 RAG 기반 분석을 기본으로 실행했지만, 현재는 Hybrid 분석이 기본값이다.

### 기본 Hybrid 실행

```bash
python -m scripts.run_analyze_local --self-consistency 3
```

기본 입력:

```text
outputs/processed/clean.jsonl
outputs/processed/merged.jsonl
outputs/processed/raw.jsonl
```

기본 출력:

```text
outputs/processed/analysis.jsonl
```

### 기존 RAG 방식 실행

기존 RAG 기반 분석은 `--legacy` 옵션으로 실행한다.

```bash
python -m scripts.run_analyze_local --legacy --self-consistency 3
```

기본 입력:

```text
outputs/processed/chunks.jsonl
```

기본 출력:

```text
outputs/processed/analysis.jsonl
```

---

## 10. `max_tokens` 기본값 상향

Hybrid holistic 평가는 한 번의 LLM 응답으로 18개 항목에 대한 JSON 결과를 출력한다.
기본 출력 토큰이 낮을 경우 후반 항목이 잘려 다음 항목들이 파싱 실패하는 문제가 있었다.

파싱 실패가 확인된 항목:

```text
C4_transition
C5_example
C5_practice
```

증상:

```text
score: null
comment: 응답 없음(파싱 실패)
routing.missing: true
```

원인은 전처리/정제 문제가 아니라 LLM 응답 출력 길이 부족이었다.

이를 해결하기 위해 `run_analyze_local.py`에 `--max-tokens` 옵션을 추가하고 기본값을 8000으로 설정했다.

### 현재 기본값

```bash
--max-tokens 8000
```

### 필요 시 명시 실행

```bash
python -m scripts.run_analyze_local \
  --self-consistency 3 \
  --max-tokens 8000
```

---

## 11. `SCHEMA.md` 계약 반영

`docs/SCHEMA.md`에 새 분석 계약을 반영했다.

반영 내용:

```text
- analysis.jsonl 기본 실행은 Hybrid
- run_analyze_local --legacy 로 기존 RAG 경로 사용 가능
- Hybrid와 Legacy RAG 모두 동일 analysis.jsonl 스키마 사용
- 새 카테고리 구조 반영
- routing.method 값 문서화
- raw_metric 4개 항목 명시
- holistic_fullcontext 14개 항목 명시
- evidence 형식 확장
```

### evidence 형식

Legacy RAG의 evidence:

```json
{"chunk_id": 12, "quote": "실제 인용"}
```

Hybrid holistic의 evidence:

```json
{"time": "09:13", "quote": "실제 인용"}
```

---

## 12. `analysis.jsonl` 스키마

Hybrid와 Legacy RAG는 동일한 `analysis.jsonl` 스키마를 따른다.

예시:

```json
{
  "lecture_id": "2026-02-02_오전",
  "file": "2026-02-02_kdt-backendj-21th.txt",
  "date": "2026-02-02",
  "session": "오전",
  "item_key": "C3_analogy",
  "category": "C3",
  "eval_type": "local",
  "score": 4,
  "verdict": "양호",
  "evidence": [{"time": "09:13", "quote": "실제 인용"}],
  "metric": null,
  "comment": "근거 기반 평가",
  "scoring_trace": {
    "raw_scores": [4, 4, 3],
    "final_score": 4,
    "agreement": 0.67
  },
  "routing": {
    "method": "holistic_fullcontext",
    "n_candidates": 14,
    "negative_evidence": false
  }
}
```

---

## 13. 실행 예시

### 1단계. 전처리

```bash
python -m scripts.run_preprocess
```

### 2단계. 정제/청킹/태깅

```bash
python -m scripts.run_refine_local \
  --file 2026-02-02_kdt-backendj-21th.txt \
  --fresh
```

### 3단계. 기본 Hybrid 분석

```bash
python -m scripts.run_analyze_local \
  --self-consistency 3
```

### 4단계. 점수 계산

```bash
python -m scripts.run_score_local
```

### 5단계. 리포트 생성

```bash
python -m scripts.run_report_local --pdf
```

---

## 14. 비교 실험용 실행

기존 결과와 수정 후 결과를 비교하려면 출력 파일을 분리한다.

```bash
python -m scripts.run_analyze_local \
  --self-consistency 3 \
  --out outputs/processed/analysis_new.jsonl
```

기존 RAG 경로와 비교하려면:

```bash
python -m scripts.run_analyze_local \
  --legacy \
  --self-consistency 3 \
  --out outputs/processed/analysis_legacy.jsonl
```

실험용 Hybrid runner를 사용할 경우:

```bash
python -m scripts.run_hybrid_eval \
  --clean outputs/processed/clean.jsonl \
  --out outputs/processed/analysis.jsonl \
  --self-consistency 3 \
  --max-tokens 8000
```

주의: `run_hybrid_eval.py`의 기본 출력은 `hybrid_analysis.jsonl`이므로, 후속 `run_score_local`과 연결하려면 `--out outputs/processed/analysis.jsonl`을 지정해야 한다.

---

## 15. 검증 명령어

### 강의당 18개 항목 생성 확인

```bash
wc -l outputs/processed/analysis.jsonl
```

예를 들어 오전/오후 2개 세션이면 총 36행이 나와야 한다.

```text
36 outputs/processed/analysis.jsonl
```

### routing.method 확인

```bash
grep -o '"method": "[^"]*"' outputs/processed/analysis.jsonl | sort | uniq -c
```

기대값:

```text
raw_metric
holistic_fullcontext
```

### 구 기준 key 잔존 확인

```bash
grep -E "C3_pace|C4_error|C5_check|C5_engage|C5_answer|C4_example|C4_practice" outputs/processed/analysis.jsonl
```

아무것도 출력되지 않아야 한다.

### 필수 필드 누락 확인

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("outputs/processed/analysis.jsonl")
required = {
    "lecture_id", "file", "date", "session",
    "item_key", "category", "eval_type",
    "score", "verdict", "evidence", "metric",
    "comment", "scoring_trace", "routing"
}

bad = []
for i, line in enumerate(path.open(encoding="utf-8"), 1):
    r = json.loads(line)
    missing = required - set(r)
    if missing:
        bad.append((i, missing))

print("total bad:", len(bad))
print("bad rows:", bad[:10])
PY
```

`total bad: 0`이면 스키마 필드 누락이 없다.

---

## 16. 기존 DoD 상태

### 1. `run_analyze_local` 기본이 Hybrid, `analysis.jsonl` 동일 스키마

상태: 완료

```text
- run_analyze_local 기본 실행이 Hybrid로 변경됨
- --legacy 옵션으로 기존 RAG 경로 보존
- Hybrid와 Legacy RAG 모두 analysis.jsonl 동일 스키마 사용
```

---

### 2. gold 2건 MAE 0.37 재현

상태: 재정의 필요

기존 `gold 2건 MAE 0.37`은 구 강의 품질 기준 기반 수치다.
현재는 `new_강의 품질 기준.pdf` 반영으로 item_key와 category 구성이 변경되었기 때문에, 기존 MAE 0.37을 새 기준에서 그대로 재현하는 것은 적절하지 않다.

변경된 항목:

```text
삭제: C4_error, C5_check, C5_engage, C5_answer
추가: C3_term_explanation, C3_concept_connection, C3_code_explanation, C4_transition
이동: C3_pace → C4_pace, C4_example → C5_example, C4_practice → C5_practice
```

따라서 다음 중 하나로 재정의해야 한다.

```text
1. 새 기준 gold 2건을 재채점한 뒤 MAE 재산출
2. 기존 gold와 공통으로 남은 항목에 대해서만 참고 MAE 출력
```

---

### 3. 산출물이 `docs/SCHEMA.md` 계약과 일치

상태: 문서 반영 완료, 실제 산출물 검증 필요

```text
- SCHEMA.md에 기본 Hybrid 분석 계약 반영
- routing.method 문서화
- raw_metric / holistic_fullcontext 구분 반영
- evidence 형식 확장 반영
```

남은 확인:

```text
- 실제 analysis.jsonl 필드 누락 여부 확인
- 구 item_key 잔존 여부 확인
- 강의당 18행 생성 여부 확인
- run_score_local / run_report_local 후속 실행 확인
```

---

## 17. 남은 작업

현재까지 완료된 작업:

```text
- 새 강의 품질 기준 18개 항목 반영
- 기본 Hybrid 분석 경로 구현
- 기존 RAG 경로 --legacy 보존
- raw metric 4항목 / holistic 14항목 라우팅 정리
- run_analyze_local 기본 Hybrid화
- max_tokens=8000 적용으로 파싱 실패 해결
- SCHEMA.md 계약 반영
```

남은 작업:

```text
1. 실제 analysis.jsonl 산출물 검증
   - 강의당 18행
   - 구 key 미포함
   - routing.method 정상 기록
   - score=null 과도 발생 없음

2. run_score_local / run_report_local 후속 실행 확인
   - scores.json 생성
   - PDF/MD 리포트 생성
   - 새 카테고리명 정상 표시

3. scripts/exp_holistic_eval.py 확인
   - 새 CHECKLIST를 동적으로 읽는지 확인
   - 구 항목 하드코딩 여부 확인

4. gold 기준 재정의
   - 기존 MAE 0.37은 구 기준 기반이므로 직접 재현 대상에서 제외
   - 새 기준 gold 재채점 또는 공통 항목 한정 MAE로 변경 필요
```

---

## 18. 요약

이번 변경의 핵심은 다음과 같다.

```text
기존:
RAG 기반 청크 검색 평가 중심
기존 강의 품질 기준 18항목
run_analyze_local 기본 RAG
일부 metric + 태깅 기반 평가

변경 후:
Hybrid 분석 기본화
new_강의 품질 기준 18항목 반영
전체 원문 holistic 평가 14항목
raw metric 결정 평가 4항목
run_analyze_local 기본 Hybrid
기존 RAG는 --legacy로 보존
analysis.jsonl 동일 스키마 유지
SCHEMA.md 계약 반영
max_tokens=8000으로 holistic 파싱 안정화
```
