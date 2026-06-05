# 역할 분담 (4인 · 고도화 단계)

> 단계 사이 계약은 [SCHEMA.md](SCHEMA.md). **계약만 지키면 4명이 병렬로 진행.**
> 규칙 기반 전처리(Step 0~2)는 완료·검증됨. 이제 모델/분석/리포트 고도화.

| | 워크스트림 | 실행 | 담당 폴더 | 입력 → 산출물 |
|---|---|---|---|---|
| **P1** | 정제 고도화 | 🔴 Colab(A100·Solar) | `src/refine/`, `notebooks/02_refine_colab.ipynb` | `merged.jsonl` → `clean.jsonl`, `chunks.jsonl` |
| **P2** | 분석 엔진 | 🔴 Colab(LLM) | `src/analyze/` | `chunks.jsonl` → `analysis.jsonl` |
| **P3** | 스코어링·검증 | 🟢 로컬(일부 LLM) | `src/scoring/` | `analysis.jsonl` + 메타(정답) → `scores.json`, eval |
| **P4** | 리포트·대시보드·인프라 | 🟢 로컬 | `src/report/`, repo/CI | `scores.json` → 리포트/대시보드 |

## P1 — 정제 고도화 (Colab)
- Colab에서 Solar-10.7B 실제 구동, 정제 프롬프트 튜닝(군더더기 제거 품질).
- 용어집 후보 추출→검수→`glossary.json` 확정, `rule:true` 항목 정리.
- 청킹 고도화: 현재 LLM 분할 → **임베딩(sentence-transformers) 기반 주제경계** 검토.
- 정제 전/후 품질 지표(필러 감소율 등) 측정.
- **계약 책임**: `clean.jsonl`, `chunks.jsonl` ([SCHEMA.md](SCHEMA.md)).

## P2 — 분석 엔진 (Colab)
- 체크리스트 18항목(`src/analyze/checklist.py`)별 프롬프트 정교화 + few-shot.
- 강의별 항목 평가 → `analysis.jsonl`(근거 인용 `chunk_id` 포함).
- 토큰 초과 대비: 항목별 관련 청크 선별(임베딩 검색), self-consistency 옵션.
- ⚠️ 실제 체크리스트 PDF(데이터 폴더)의 세부 기준을 `checklist.py` description에 반영.
- **계약 책임**: `analysis.jsonl`.

## P3 — 스코어링·검증 (로컬)
- `src/scoring/scoring.py`: 카테고리 가중→종합점수. `CATEGORY_WEIGHTS` 확정.
- 강사/세션 비교, 주차별 시계열 추이.
- `src/scoring/evaluate.py`: **메타데이터를 정답으로** 분석 정확도 검증(커버리지·강사·주제).
  ⚠️ 메타는 정답/검증 전용 — 분석 input에 절대 넣지 않음.
- **계약 책임**: `scores.json`, eval 리포트.

## P4 — 리포트·대시보드·인프라 (로컬)
- `src/report/build.py`: 강의별 리포트(MD→PDF/DOCX, ReportLab/python-docx).
- `src/report/dashboard.py`: Streamlit 대시보드(점수·레이더·근거 드릴다운).
- 재현성/CI: manifest, 버전 핀, repo 브랜치·PR 운영, 발표자료/시연영상.

## 공통 규칙
- 단계 산출물은 모두 `outputs/` (git 미포함). 데이터·키 커밋 금지.
- 모델 호출은 `generate_fn` 주입 패턴 유지 → GPU 없이 `scripts/smoke_*.py`로 배관 검증.
- 스키마 변경은 [SCHEMA.md](SCHEMA.md) 먼저 수정 후 공유.

## 마일스톤 정렬 (중간점검=2주차)
단일 강의 1편 end-to-end: P1 정제 1편 → P2 18항목 분석 → P3 점수 1건 → P4 리포트/시연.
