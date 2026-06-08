"""프로젝트 공통 설정: 데이터 경로, 상수, JVM(KoNLPy) 경로 해석.

모든 모듈은 여기서 경로/상수를 가져다 쓴다. 실제 강의 데이터는 git에 포함되지
않으므로(.gitignore), 로컬 `AI_Lecture_Analysis_Report_Generator/` 폴더에 원본을
배치한 뒤 실행한다.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# ── 경로 ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# .env 자동 로드(있으면) — UPSTAGE_API_KEY 등. python-dotenv 없으면 조용히 패스.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

DATA_ROOT = PROJECT_ROOT / "AI_Lecture_Analysis_Report_Generator"
SCRIPT_DIR = DATA_ROOT / "강의 스크립트"
METADATA_CSV = DATA_ROOT / "강의 메타데이터.csv"

OUTPUT_DIR = PROJECT_ROOT / "outputs"
EDA_DIR = OUTPUT_DIR / "eda"
FIG_DIR = EDA_DIR / "figures"

# 전처리 파이프라인 산출물(JSONL 등) — 원본 텍스트 파생물이므로 git 미포함
PROCESSED_DIR = OUTPUT_DIR / "processed"

# ── 화자(Step 2) ───────────────────────────────────────────────────────
# 제공 데이터는 사실상 강사 단일화자(강사 글자 비중 ~92%, 소수 '학생' 라벨은
# STT 오인식 아티팩트). True 면 build_speaker_map 이 전 화자를 '강사'로 라벨한다.
# 진짜 다화자 데이터가 들어오면 False 로 바꾸면 학생N 매핑이 살아난다.
SINGLE_SPEAKER = True

# ── 발화 병합(Step 2) 파라미터 ─────────────────────────────────────────
# 같은 화자 연속 발화를 하나의 블록으로 합칠 때의 시간 간격 임계값(초).
# 데이터 측정: 동일화자 연속 gap 중앙값 10s, 81%가 ≤15s, 30s 초과는 2%(주제전환 추정).
# → 2~3s(원안)는 과분할이라 20s로 상향. 폭주 방지용 블록 상한도 둠.
MERGE_GAP_SEC = 20.0
MERGE_MAX_BLOCK_SEC = 150.0
MERGE_MAX_BLOCK_CHARS = 2000

# ── 정제/모델(Step 3~5) 백엔드 ─────────────────────────────────────────
# Solar 를 어디서 돌릴지 선택(둘 다 generate_fn(messages)->str 동일 인터페이스):
#   "hf"      : HuggingFace 오픈모델(SOLAR-10.7B-Instruct) — Colab GPU 필요
#   "upstage" : Upstage Solar API(클라우드) — UPSTAGE_API_KEY 필요, GPU 불필요(로컬 가능)
MODEL_BACKEND = "upstage"

# (hf 백엔드) HuggingFace 오픈모델
MODEL_ID = "upstage/SOLAR-10.7B-Instruct-v1.0"
# 재현성: 모델 가중치 revision 을 커밋 해시로 고정 권장(HF 페이지에서 확인 후 입력).
# None 이면 main 최신 — 팀 재현성을 위해 실제 운영 시 반드시 핀할 것.
MODEL_REVISION = None

# (upstage 백엔드) Upstage Solar API — OpenAI 호환. 키는 .env 의 UPSTAGE_API_KEY.
# 엔드포인트·모델명은 Upstage 콘솔/문서 기준(바뀌면 여기만 수정).
UPSTAGE_BASE_URL = "https://api.upstage.ai/v1"
UPSTAGE_MODEL = "solar-pro2"   # 대안: solar-pro, solar-mini

# 결정적 생성(재현성): 그리디/temperature=0 + 시드 고정.
GEN_MAX_NEW_TOKENS = 1024
GEN_DO_SAMPLE = False
SEED = 42

# Step 4 정제: 인접 블록을 묶는 섹션 최대 글자 수(맥락 보존 단위).
# Solar 4k 컨텍스트 + 용어집/이전요약/출력 여유를 고려해 보수적으로.
SECTION_MAX_CHARS = 2500
# 슬라이딩 윈도우: 다음 섹션에 넘길 직전 섹션 요약 최대 글자.
CONTEXT_SUMMARY_MAX_CHARS = 400

# ── 임베딩(태깅·청킹, Step 5 / §9) ─────────────────────────────────────
# 백엔드 선택(둘 다 embed_fn(texts)->np.ndarray[n,d] 동일 인터페이스):
#   "kure"    : nlpai-lab/KURE-v1 (sentence-transformers) — 품질 1순위(§11), GPU 권장·CPU 가능, ~2GB 다운로드
#   "upstage" : Upstage 임베딩 API — 다운로드·GPU 불필요(UPSTAGE_API_KEY). openai 패키지만 있으면 로컬 OK
EMBED_BACKEND = "upstage"
EMBED_MODEL_ID = "nlpai-lab/KURE-v1"          # (kure) 대안: BAAI/bge-m3, BM-K/KoSimCSE-roberta
UPSTAGE_EMBED_MODEL = "embedding-passage"     # (upstage) 대안: solar-embedding-1-large-passage
# 임베딩 기반 토픽 분할(TextTiling-lite)
SEG_DEPTH_C = 0.4        # 경계 임계: depth > mean + c*std
SEG_MIN_SENTS = 3        # 청크 최소 문장 수
SEG_MAX_SENTS = 25       # 청크 최대 문장 수(폭주 방지)
# 평가항목 태깅 — 항목당 top-k 검색(표준 RAG: dense retrieve → ⑥ LLM judge).
# "임계값 넘는 거 전부"(과태깅) 대신 항목마다 가장 관련된 top-k 만 추린다. 문헌: RubricRAG·DAT.
TAG_TOP_K = 5                # 항목당 검색할 관련 청크 수(RubricRAG k=5~20)
# 후보 최소 유사도 — 변별력 있는 값이어야 부정 증거(항목 부재) 신호가 산다.
# 0.35은 모든 항목이 top-k를 억지로 채움 → 0.45(실측: 관련 0.45+, 무관 baseline ~0.35-0.45).
TAG_RETRIEVE_FLOOR = 0.45    # 이하면 무관 → 후보에서 제외(항목 부재면 top-k 미달=부정 증거)
# 고정밀 cue 있으면 floor 를 여기로 낮춰 구제 — 저sim 진짜 인스턴스(예: '처럼' 비유) 살림.
TAG_FLOOR_KW = 0.33         # 키워드 hit 시 적용하는 낮은 floor
# 랭킹 가산점 — cue 있는 진짜가 generic 임베딩 FP 위로 가게. 0.15면 cue(sim 0.42)가
# 무cue 노이즈(sim 0.53) 위로 올라가 LLM 이 진짜 근거를 먼저 본다(노이즈 감소).
TAG_KEYWORD_BONUS = 0.15
INTRO_RATIO = 0.20           # 도입부 = 강의 앞 20%
OUTRO_RATIO = 0.20           # 종료부 = 강의 뒤 20%

# ── 개요 추출(Step 3, §2) ──────────────────────────────────────────────
OVERVIEW_TOP_KEYWORDS = 15   # 강의별 핵심 키워드 수(KoNLPy)

# ── 분석 엔진(Step 6, P2) — 잠정값(§2차 EDA 캘리브레이션) ───────────────
ANALYZE_EVIDENCE_K = 5       # 항목별 LLM 에 넣을 근거 청크 최대 수
ANALYZE_MAX_EXPAND = 1       # 🟠 local 문맥확장 최대 횟수(needs_more 반환 시)
ANALYZE_GLOBAL_SAMPLE = 8    # 🔴 global 압축뷰에 넣을 샘플 청크 수
ANALYZE_SELF_CONSISTENCY = 1 # 항목당 LLM 채점 반복수(>1=다수결, 비결정성·놓침 완화)
ANALYZE_SC_TEMPERATURE = 0.4 # self-consistency 샘플 다양성용 온도(반복수>1일 때)
PACE_CPM_LOW = 300           # 발화속도 적정 하한(분당 글자) — 잠정
PACE_CPM_HIGH = 700          # 적정 상한 — 잠정
FILLER_RATE_HIGH = 0.15      # 필러율 '높음' 기준 — 잠정

# ── 도메인 상수 ────────────────────────────────────────────────────────
# 오전/오후 세션 경계 (메타데이터: 오전 09:00~12:00, 오후 13:00~18:00)
SESSION_SPLIT_HOUR = 13

# 언어 표현 품질(체크리스트 카테고리 1)과 직접 연결되는 군더더기/필러 표현.
# STT 특성상 구어체 간투사가 많아, '불필요한 반복 표현' 분석의 1차 신호로 사용.
FILLER_WORDS = [
    "음", "어", "아", "자", "이제", "그래서", "그러면", "그러니까", "근데",
    "그냥", "막", "뭐", "이렇게", "저렇게", "약간", "좀", "인제", "요",
    "네", "예", "거든요", "있잖아요",
]

# 한국어 분석 시 제거할 1차 불용어(빈도 분석 노이즈 제거용). 필요 시 확장.
# Okt가 명사로 오분류하는 부사/대명사/수량 표현을 포함해 도메인 키워드를 부각.
STOPWORDS = set(FILLER_WORDS) | {
    "것", "수", "때", "거", "게", "걸", "또", "더", "등", "및", "은", "는",
    "이", "가", "을", "를", "에", "의", "도", "로", "와", "과", "한", "수가",
    "안", "이런", "그런", "저런", "여기", "거기", "저기", "우리", "저희", "여러분",
    # 내용어가 아닌 빈출 명사(부사·수량·지시 표현)
    "지금", "다음", "가지", "하나", "살짝", "한번", "현재", "부분", "경우",
    "정도", "얘기", "생각", "자기", "느낌", "처음", "마지막", "사람", "그것",
    "이것", "저것", "가요", "여기서", "이거", "저거", "그거", "전부", "이번",
}


def resolve_jvm_path() -> str | None:
    """KoNLPy(JPype)용 libjvm 경로를 안정적으로 해석한다.

    JPype 1.7 + 최신 JDK 조합에서 konlpy 내부 기본 경로 탐지가 bytes를 반환해
    터지는 알려진 버그가 있어, 명시적 str 경로를 만들어 넘긴다.
    `Okt(jvmpath=resolve_jvm_path())` 형태로 사용.
    반환값이 None이면 KoNLPy 기본 동작에 맡긴다.
    """
    java_home = os.environ.get("JAVA_HOME")
    if not java_home:
        try:
            java_home = subprocess.check_output(
                ["/usr/libexec/java_home"], text=True
            ).strip()
        except Exception:
            return None
    candidate = Path(java_home) / "lib" / "server" / "libjvm.dylib"
    return str(candidate) if candidate.exists() else None


def ensure_output_dirs() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
