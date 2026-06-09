# 데이터 계약 (JSONL 스키마)

파이프라인 단계 사이의 **인터페이스**다. 이 계약만 지키면 P1~P4가 서로 안 막히고 병렬로 작업할 수 있다.
필드를 바꿔야 하면 **먼저 이 문서를 고치고 팀에 공유** → 그 다음 코드.

```
txt ─①─ raw.jsonl ─②─ merged.jsonl ─③④─ clean.jsonl ─⑤─ chunks.jsonl ─P2─ analysis.jsonl ─P3─ scores.json ─P4─ reports/
                                                                            메타데이터(정답) ─P3─ eval
```

> ⚠️ 모든 산출물은 원본 텍스트 파생물 → `outputs/` (git 미포함). 메타데이터는 **정답/검증용**이며 분석 input에 넣지 않는다.

---

## raw.jsonl  (Step1, 규칙)
발화 1건 = 1행. 원본 불변, 전역 `idx`로 추적.
```json
{"idx": 0, "file": "2026-02-02_...txt", "date": "2026-02-02", "course_id": "kdt-backendj-21th",
 "line_no": 1, "time": "09:11:17", "sec_of_day": 33077, "hour": 9, "session": "오전",
 "speaker_id": "b54f46b0", "text": "원문 그대로", "malformed": false}
```
- `time`은 12h→24h 보정값. `session`은 24h 기준(오전<13시).

## merged.jsonl  (Step2, 규칙)
같은 화자 연속 발화를 블록으로 병합. `raw_ref`로 원본 idx 추적.
```json
{"block_id": 0, "file": "...", "date": "2026-02-02", "session": "오전",
 "speaker_id": "b54f46b0", "speaker_role": "강사", "start_time": "09:11:17", "end_time": "09:13:41",
 "start_sec": 33077, "end_sec": 33221, "dur_sec": 144, "n_utts": 16,
 "text": "병합된 발화", "raw_ref": [0,1,2,...]}
```
- `speaker_role`: `강사`/`학생N`/`미상`. 단, 제공 데이터는 단일화자(`config.SINGLE_SPEAKER=True`)라 전부 `강사`. 보조 테이블 `speaker_map.json` = `{file: {speaker_id: role}}`(수동 보정 가능).

## glossary.json  (Step3, 모델→사람 검수)
```json
{"corrections": [{"wrong": "잡바", "correct": "Java", "rule": true}],
 "terms": ["Java", "NIO", "테이블", "조인"]}
```
- `rule:true` → 정제 모델 호출 **전에** 결정적 치환. 후보는 `glossary_candidates.json`에서 검수해 옮긴다.

## clean.jsonl  (Step4, 모델)
섹션(인접 블록 묶음) 단위 정제 결과.
```json
{"section_id": 0, "file": "...", "date": "2026-02-02", "session": "오전",
 "raw_ref": [0,1,...], "start_time": "09:11:17", "end_time": "09:20:03",
 "clean_text": "문어체로 정제된 본문", "summary": "다음 섹션용 한두 문장 요약"}
```

## overview.json  (Step3, §2) — 강의 개요 (정제 전역 맥락)
강의(=`date_session`)별 키워드+주제 아웃라인. 메타 대신 스크립트에서 직접 추출.
```json
{"2026-02-02_오전": {"keywords": ["스트림","입출력","자바"], "outline": ["자바 IO 개요","스트림 실습"]}}
```

## chunks.jsonl  (Step5, 임베딩) — 분석부 입력
임베딩 기반 토픽 분할(`chunk_embed.py`) + **평가항목 태깅(`eval_tags`)** 포함.
```json
{"chunk_id": 0, "lecture_id": "2026-02-02_오전", "file": "...", "date": "2026-02-02",
 "session": "오전", "pos": 0.05, "clean_text": "...", "raw_ref": [0,1,...],
 "start_time": "09:11:17", "end_time": "09:20:03",
 "eval_tags": [{"item_key": "C5_check", "sim": 0.62, "score": 0.67, "cue": "되셨어요"}]}
```
- `pos`: 강의 내 상대 위치(0~1, 도입/종료 항목 게이트용).
- `eval_tags`: §9 항목당 top-k 검색 결과(다중 라벨, 0개 허용=항목 부재). `item_key`는 `checklist.py` 기준.
  - `sim`: dense 임베딩 유사도(랭킹 주신호). `score`: sim + 키워드 가산점. `cue`: 매칭된 시드 키워드(없으면 null=의미만으로 검색). 항목당 최대 `TAG_TOP_K`개(강의 단위).
  - ⑤는 recall 후보생성기 — 정밀 판정(FP 제거)은 ⑥ 분석의 LLM 이 한다.
- (구버전 LLM 청킹 `chunk.py`는 fallback — `topic` 필드 사용.)

## analysis.jsonl  (P2, 모델) — 4갈래 라우팅 평가
강의(=`date_session`)별 체크리스트 18항목 평가. 항목 1건 = 1행. 항목은 `eval_type`으로 라우팅돼
서로 다른 입력을 본다(검색형=태깅 청크, 위치형=도입/종료, 전역형=압축뷰, 지표형=선계산 숫자).
```json
{"lecture_id": "2026-02-02_오전", "file": "...", "date": "2026-02-02", "session": "오전",
 "item_key": "C3_analogy", "category": "C3", "eval_type": "local",
 "score": 4, "verdict": "양호",
 "evidence": [{"chunk_id": 12, "quote": "실제 인용"}],
 "metric": null,
 "comment": "근거 기반 평가",
 "scoring_trace": {"raw_scores": [4,4,3], "final_score": 4, "agreement": 0.67},
 "routing": {"n_candidates": 3, "expanded": 0,
             "candidate_chunk_ids": [12,15], "context_chunk_ids": [],
             "negative_evidence": false, "cross_checked": false}}
```
- `item_key`/`category`/`eval_type`은 `src/analyze/checklist.py`가 진실원천(18개 고정). `score`는 1~5(`null`=N/A).
- `verdict`: `우수/양호/보통/미흡/없음` 외에 `근거 부족`(고득점인데 인용 근거가 없어 자동 강등), `N/A`(지표 계산 불가로 평가 보류)도 가능.
- `metric`: 지표형(`metric`)이면 `{"name": "pace", "value": 312.5}`, 그 외 `null`. 단 전역형이 규칙 지표와 혼합되면(C1_consistency·C1_completeness) 여기에 해당 지표값이 실린다.
- `scoring_trace`: 점수 안정성 추적 — `raw_scores`(self-consistency 원점수 목록), `final_score`(최종 채택 점수), `agreement`(최종값과 일치한 표본 비율 0~1). 자동 강등 시 `evidence_adjusted: true`, 전역 규칙 혼합 시 `rule_score`(규칙 점수)가 추가된다. samples=1이면 `raw_scores`는 1개.
- `routing`: 라우팅 메타 — `n_candidates`(후보 청크 수), `expanded`(문맥확장 횟수 0~2), `candidate_chunk_ids`(근거 후보 청크 id), `context_chunk_ids`(문맥확장으로 추가된 청크 id), `negative_evidence`(태그 0 부정 증거), `cross_checked`(태그 0일 때 교차검증 수행 여부), `rule_mixed`(전역형 규칙·LLM 혼합 여부, 해당 시).

## scores.json  (P3, 규칙) — 항목별 가중
```json
{"lectures": {"2026-02-03_오전": {"date": "2026-02-03", "session": "오전",
   "category_scores": {"C1": 85.7, "C2": 27.3, "C3": 27.5, "C4": 34.4, "C5": 8.3},
   "total_score": 33.9, "n_na": 0,
   "items": [{"item_key": "C1_repetition", "category": "C1", "score": 5,
              "norm": 100.0, "weight": 3, "negative": false}]}},
 "summary": {"n_lectures": 2, "avg_total": 32.8, "by_date": {"2026-02-03": 32.8}}}
```
- 점수 0~100 정규화(score 1~5 → 0~100). **항목별 가중**(`checklist.weight` high3/mid2/low1) 평균 — 카테고리 균등 ❌.
- `n_na`: N/A(score=null) 항목 수(가중에서 제외). `items[].negative`: 부정 증거 여부.
- `summary.by_date`: 일자/주차별 평균(추이).

## reports/  (P4)
강의별 `report_{lecture_id}.md` (→ PDF/DOCX), Streamlit 대시보드.
