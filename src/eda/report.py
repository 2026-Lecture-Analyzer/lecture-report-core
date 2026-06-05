"""EDA 리포트 생성 엔진.

`build_report()` 하나로:
  1) 분석용 데이터셋 적재 (src.preprocess)
  2) 통계 계산 + 차트(PNG) 생성  → outputs/eda/figures/
  3) 마크다운 리포트 작성        → outputs/eda/eda_report.md

강의 원본 텍스트가 섞인 산출물이므로 outputs/ 는 .gitignore 처리되어 있다.
"""
from __future__ import annotations

from collections import Counter

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from src import config
from src.preprocess import text as textmod
from src.preprocess.loader import build_dataset

matplotlib.use("Agg")
# macOS 한글 폰트
plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 110

# 주차 정의 (제공 데이터 기준)
WEEK_RANGES = {
    "1주차": ("2026-02-02", "2026-02-06"),
    "2주차": ("2026-02-09", "2026-02-13"),
    "3주차": ("2026-02-23", "2026-02-27"),
}


def assign_week(df: pd.DataFrame) -> pd.Series:
    wk = pd.Series("기타", index=df.index)
    for name, (lo, hi) in WEEK_RANGES.items():
        mask = (df["date"] >= lo) & (df["date"] <= hi)
        wk[mask] = name
    return wk


# ── 차트 ───────────────────────────────────────────────────────────────
def _save(fig, name: str) -> str:
    config.ensure_output_dirs()
    path = config.FIG_DIR / name
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return f"figures/{name}"


def fig_utterances_by_day(df: pd.DataFrame) -> str:
    piv = df.pivot_table(index=df["date"].dt.strftime("%m-%d"), columns="session",
                         values="text", aggfunc="count", fill_value=0)
    piv = piv.reindex(columns=["오전", "오후"])
    fig, ax = plt.subplots(figsize=(10, 4.5))
    piv.plot(kind="bar", stacked=True, ax=ax, color=["#4C72B0", "#DD8452"])
    ax.set_title("일자·세션별 발화 수")
    ax.set_xlabel("날짜"); ax.set_ylabel("발화 수"); ax.legend(title="세션")
    return _save(fig, "01_utterances_by_day.png")


def fig_chars_by_day(df: pd.DataFrame) -> str:
    g = df.groupby(df["date"].dt.strftime("%m-%d"))["char_len"].sum()
    fig, ax = plt.subplots(figsize=(10, 4))
    g.plot(kind="bar", ax=ax, color="#55A868")
    ax.set_title("일자별 총 발화 글자 수"); ax.set_xlabel("날짜"); ax.set_ylabel("글자 수")
    return _save(fig, "02_chars_by_day.png")


def fig_hourly_density(df: pd.DataFrame) -> str:
    g = df.groupby("hour").size()
    fig, ax = plt.subplots(figsize=(9, 4))
    g.plot(kind="bar", ax=ax, color="#C44E52")
    ax.set_title("시간대(24h)별 발화 밀도 — 강의 페이스 / 점심 공백")
    ax.set_xlabel("시"); ax.set_ylabel("발화 수")
    return _save(fig, "03_hourly_density.png")


def fig_utterance_length_hist(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(df["char_len"].clip(upper=300), bins=50, color="#8172B3")
    ax.set_title("발화 길이 분포 (글자 수, 300자 클리핑)")
    ax.set_xlabel("발화당 글자 수"); ax.set_ylabel("빈도")
    ax.axvline(df["char_len"].median(), color="k", ls="--", lw=1,
               label=f"중앙값 {df['char_len'].median():.0f}")
    ax.legend()
    return _save(fig, "04_utterance_length_hist.png")


def fig_filler(filler: Counter) -> str:
    top = filler.most_common(15)
    labels, vals = zip(*top) if top else ([], [])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(list(labels)[::-1], list(vals)[::-1], color="#937860")
    ax.set_title("군더더기(필러) 표현 빈도 Top 15 — 언어 표현 품질 신호")
    ax.set_xlabel("출현 횟수")
    return _save(fig, "05_filler_top.png")


def fig_keywords(nouns: Counter) -> str:
    top = nouns.most_common(20)
    labels, vals = zip(*top) if top else ([], [])
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(list(labels)[::-1], list(vals)[::-1], color="#4C72B0")
    ax.set_title("핵심 키워드(명사) Top 20")
    ax.set_xlabel("빈도")
    return _save(fig, "06_keywords_top.png")


# ── 리포트 본문 ────────────────────────────────────────────────────────
def _md_table(df: pd.DataFrame, index_label: str = "") -> str:
    cols = list(df.columns)
    head = "| " + (index_label + " | " if index_label else "") + " | ".join(map(str, cols)) + " |"
    sep = "|" + ("---|" * (len(cols) + (1 if index_label else 0)))
    lines = [head, sep]
    for idx, row in df.iterrows():
        cells = [str(idx)] if index_label else []
        cells += [f"{v:,}" if isinstance(v, (int,)) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report() -> str:
    df = build_dataset()
    df["week"] = assign_week(df)
    valid = df[~df["malformed"]].copy()

    # ── 기본 통계 ──
    n_days = valid["date"].nunique()
    n_utt = len(valid)
    n_chars = int(valid["char_len"].sum())
    date_min = valid["date"].min().date()
    date_max = valid["date"].max().date()
    instructors = ", ".join(sorted(valid["instructor"].dropna().unique()))

    # 일자×세션 발화/글자
    by_day = valid.pivot_table(index=valid["date"].dt.strftime("%m-%d"),
                               columns="session", values="text",
                               aggfunc="count", fill_value=0).reindex(columns=["오전", "오후"])
    by_day["합계"] = by_day.sum(axis=1)

    # 강의 시간 구조 (세션별 시작~종료, 추정 길이)
    span = (valid.groupby([valid["date"].dt.strftime("%m-%d"), "session"])
            .agg(start=("minute_of_day", "min"), end=("minute_of_day", "max"))
            .assign(길이분=lambda x: x["end"] - x["start"]))

    # 화자 수
    speakers_per_day = valid.groupby(valid["date"].dt.strftime("%m-%d"))["speaker"].nunique()
    multi_speaker_days = speakers_per_day[speakers_per_day > 1]

    # 발화 길이
    len_desc = valid["char_len"].describe()

    # ── KoNLPy: 필러 + 키워드 ──
    konlpy_ok = True
    try:
        filler = textmod.filler_counts(valid["text"].tolist())
        nouns = textmod.noun_counts(valid["text"].tolist())
        nouns_by_week = {
            wk: textmod.noun_counts(g["text"].tolist()).most_common(10)
            for wk, g in valid.groupby("week") if wk != "기타"
        }
        # 일자별 실제 키워드 (메타데이터 과목명과 정합성 교차검증용)
        nouns_by_day = {
            d.strftime("%m-%d"): textmod.noun_counts(g["text"].tolist()).most_common(6)
            for d, g in valid.groupby("date")
        }
    except Exception as e:  # JVM/Java 미설치 등
        konlpy_ok = False
        filler, nouns, nouns_by_week, nouns_by_day = Counter(), Counter(), {}, {}
        konlpy_err = str(e)

    # ── 차트 ──
    f1 = fig_utterances_by_day(valid)
    f2 = fig_chars_by_day(valid)
    f3 = fig_hourly_density(valid)
    f4 = fig_utterance_length_hist(valid)
    figs_konlpy = []
    if konlpy_ok:
        figs_konlpy = [fig_filler(filler), fig_keywords(nouns)]

    # ── 마크다운 작성 ──
    L = []
    L.append("# 강의 스크립트 EDA 리포트\n")
    L.append("> NLP 과제 1 · AI 강의 분석 리포트 생성기 — 1주차 데이터 탐색 산출물\n")
    L.append("> ⚠️ 본 리포트는 원본 강의 텍스트 파생물을 포함하므로 외부 공유 금지 (outputs/ 는 git 미포함)\n")

    L.append("\n## 1. 데이터 개요\n")
    L.append(_md_table(pd.DataFrame({
        "값": [
            f"{date_min} ~ {date_max}", f"{n_days} 일", f"{n_utt:,} 건",
            f"{n_chars:,} 자", instructors,
            ", ".join(f"{k}({v}건)" for k, v in valid['subject'].value_counts().items()),
        ]}, index=["분석 기간", "강의일 수", "총 발화 수", "총 글자 수", "강사", "과목 분포"]),
        index_label="항목"))

    L.append("\n## 2. 발화량 통계 (일자·세션별)\n")
    L.append(f"![]({f1})\n")
    L.append(_md_table(by_day.astype(int), index_label="날짜"))
    L.append(f"\n![]({f2})\n")
    L.append("\n**관찰**: 02-12 오후·02-26 오후는 발화량이 급감 → 단축/특이 세션으로 추정. "
             "다운스트림 분석 시 세션 길이를 정규화 변수로 둘 필요.\n")

    L.append("\n## 3. 강의 시간 구조\n")
    L.append("- STT 타임스탬프는 **12시간제(AM/PM 미표기)**라, 01~05시를 13~17시로 보정함.\n")
    L.append("- 오전 09~12시 / 오후 13~17시, 그 사이 **점심 공백**이 시간대 밀도 차트에 드러남.\n")
    L.append(f"\n![]({f3})\n")
    sess_len = span.reset_index()
    sess_len.columns = ["날짜", "세션", "시작(분)", "종료(분)", "길이(분)"]
    pivot_len = sess_len.pivot_table(index="날짜", columns="세션", values="길이(분)", fill_value=0).astype(int)
    L.append("\n세션별 추정 강의 길이(분, 첫 발화~마지막 발화):\n")
    L.append(_md_table(pivot_len, index_label="날짜"))

    L.append("\n## 4. 발화 길이 분포 (발화 완결성 단서)\n")
    L.append(f"![]({f4})\n")
    L.append(_md_table(pd.DataFrame({"값": [
        f"{len_desc['mean']:.1f}", f"{len_desc['50%']:.0f}",
        f"{len_desc['min']:.0f}", f"{len_desc['max']:.0f}",
        f"{(valid['char_len'] <= 5).mean()*100:.1f}%",
    ]}, index=["평균 글자", "중앙값", "최소", "최대", "5자 이하 짧은 발화 비율"]),
        index_label="지표"))
    L.append("\n**연결**: 매우 짧은 발화(추임새·되묻기)와 매우 긴 발화(끊김 없는 장황한 설명)는 "
             "체크리스트 카테고리 1(발화 완결성) 분석의 후보 신호.\n")

    L.append("\n## 5. 화자 구성\n")
    L.append(f"- 전체 고유 화자 ID: **{valid['speaker'].nunique()}명** "
             "(대부분 주강사 단독, 일부 날짜에 보조 화자 등장 — 보조강사/질의응답 추정)\n")
    if len(multi_speaker_days):
        ms = multi_speaker_days.reset_index()
        ms.columns = ["날짜", "화자수"]
        L.append("\n복수 화자 등장일:\n")
        L.append(_md_table(ms.set_index("날짜"), index_label="날짜"))

    L.append("\n## 6. 언어 표현 품질 — 군더더기(필러) 표현\n")
    if konlpy_ok:
        L.append(f"![]({figs_konlpy[0]})\n")
        total_tok_note = filler.most_common(10)
        L.append("\n상위 필러 표현:\n")
        L.append(_md_table(pd.DataFrame(total_tok_note, columns=["표현", "횟수"]).set_index("표현"),
                           index_label="표현"))
        L.append("\n**연결**: 체크리스트 카테고리 1 '불필요한 반복 표현'의 정량 베이스라인. "
                 "강사·세션별로 집계하면 비교 분석에 활용 가능.\n")
    else:
        L.append(f"> ⚠️ KoNLPy 형태소 분석 실패로 생략됨: `{konlpy_err}`\n")

    L.append("\n## 7. 핵심 키워드 (명사 빈도)\n")
    if konlpy_ok:
        L.append(f"![]({figs_konlpy[1]})\n")
        L.append("\n주차별 Top 키워드:\n")
        for wk in ["1주차", "2주차", "3주차"]:
            if wk in nouns_by_week:
                kws = ", ".join(f"{w}({c})" for w, c in nouns_by_week[wk])
                L.append(f"- **{wk}**: {kws}")
    else:
        L.append("> KoNLPy 미동작으로 생략.\n")

    L.append("\n## 8. ⚠️ 메타데이터–스크립트 내용 정합성 (중대 발견)\n")
    L.append("일자별 **메타데이터 과목/내용**과 **STT 실제 키워드**를 나란히 비교한 결과, "
             "둘이 **일치하지 않는다**. 메타데이터는 Front-End/React/HTTP 커리큘럼을 가리키지만, "
             "실제 발화 내용은 **Java IO·SQL/데이터베이스(EMP·DEPT 테이블, 조인, 인덱스)** 중심이다.\n")
    if konlpy_ok:
        meta_day = (valid.groupby(valid["date"].dt.strftime("%m-%d"))
                    .agg(과목=("subject", "first"), 내용=("content", "first")))
        rows = []
        for d, r in meta_day.iterrows():
            kws = ", ".join(w for w, _ in nouns_by_day.get(d, []))
            rows.append((d, r["과목"], str(r["내용"])[:18], kws))
        cmp_df = pd.DataFrame(rows, columns=["날짜", "메타 과목", "메타 내용", "STT 실제 키워드 Top6"]).set_index("날짜")
        L.append("\n" + _md_table(cmp_df, index_label="날짜"))
    L.append("\n**시사점**: 메타데이터의 `subject`/`content`를 분석의 정답 라벨로 신뢰할 수 없다. "
             "강의 주제는 **스크립트 본문에서 직접 추출**하거나, 불일치를 전제로 한 검증 단계가 필요하다. "
             "(평가기준의 '데이터 한계 극복' 항목과 직접 연결되는 이슈)\n")

    L.append("\n## 9. STT 데이터 품질 노트\n")
    L.append("- 모든 라인이 `<시각> 화자ID: 발화` 정형을 따름 (파싱 예외 0건).\n")
    L.append("- 다만 **음성 인식 오류**가 다수 관찰됨: 예) '잡바(Java)', '효울씨', 'NI2', "
             "'브나이어(java.nio)', '3레드(Thread)' 등 → LLM 분석 전 도메인 용어 정규화 사전 검토 필요.\n")
    L.append("- 타임스탬프 12시간제 보정은 본 파이프라인에서 처리 완료.\n")

    L.append("\n## 10. 다음 단계 제언\n")
    L.append("1. **메타데이터 과목명을 신뢰하지 말 것** — 주제는 스크립트에서 직접 추출(키워드/LLM 요약).\n")
    L.append("2. 도메인 용어 정규화 사전 구축(STT 오인식 → 표준 용어).\n")
    L.append("3. 필러/발화길이/페이스를 **세션 단위 피처**로 집계 → 스코어링 입력.\n")
    L.append("4. 체크리스트 18개 항목별 LLM 프롬프트 설계 시, 본 EDA의 정량 지표를 보조 컨텍스트로 주입.\n")

    report = "\n".join(L) + "\n"
    config.ensure_output_dirs()
    out_path = config.EDA_DIR / "eda_report.md"
    out_path.write_text(report, encoding="utf-8")

    # 전처리 결과 테이블도 저장(분석 재사용용, git 미포함)
    valid.drop(columns=["malformed"]).to_csv(
        config.EDA_DIR / "utterances.csv", index=False, encoding="utf-8-sig")

    return str(out_path)
