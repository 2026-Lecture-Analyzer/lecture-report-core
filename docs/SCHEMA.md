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
- `speaker_role`: `강사`/`학생N`/`미상`. 보조 테이블 `speaker_map.json` = `{file: {speaker_id: role}}`(수동 보정 가능).

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

## chunks.jsonl  (Step5, 모델) — 분석부 입력
주제 단위 청크. P2의 입력.
```json
{"chunk_id": 0, "section_id": 0, "file": "...", "date": "2026-02-02", "session": "오전",
 "topic": "자바 IO 패키지 개요", "clean_text": "...", "raw_ref": [0,1,...],
 "start_time": "09:11:17", "end_time": "09:20:03"}
```

## analysis.jsonl  (P2, 모델)
강의(=`date_session`)별 체크리스트 18항목 평가. 항목 1건 = 1행.
```json
{"lecture_id": "2026-02-02_오전", "file": "...", "date": "2026-02-02", "session": "오전",
 "item_key": "C1_repetition", "category": "C1", "score": 4, "verdict": "양호",
 "evidence": [{"chunk_id": 12, "quote": "실제 인용"}], "comment": "근거 기반 평가"}
```
- `item_key`/`category`는 `src/analyze/checklist.py`가 진실원천(18개 고정). `score`는 1~5.

## scores.json  (P3, 규칙)
```json
{"lectures": {"2026-02-02_오전": {"date": "2026-02-02", "session": "오전",
   "category_scores": {"C1": 75.0, "C2": 60.0, "C3": 80.0, "C4": 55.0, "C5": 50.0},
   "total_score": 64.0}}}
```
- 점수는 0~100 정규화. 가중치 `CATEGORY_WEIGHTS`(기본 균등).

## reports/  (P4)
강의별 `report_{lecture_id}.md` (→ PDF/DOCX), Streamlit 대시보드.
