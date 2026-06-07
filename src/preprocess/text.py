"""한국어 텍스트 정제 · 토큰화 · 군더더기(필러) 분석.

KoNLPy(Okt) 형태소 분석기를 사용한다. JPype/JDK 호환 이슈를 피하려고
`config.resolve_jvm_path()`로 명시적 JVM 경로를 넘긴다.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from functools import lru_cache
from typing import TYPE_CHECKING

from src import config

if TYPE_CHECKING:
    from konlpy.tag import Okt

logger: logging.Logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")


@lru_cache(maxsize=1)
def get_okt() -> "Okt":
    """Okt 형태소 분석기 싱글턴. 최초 호출 시 JVM 기동(수 초 소요)."""
    logger.info("Okt 형태소 분석기 초기화 (JVM 기동 중, 최초 호출 시 수 초 소요)")
    from konlpy.tag import Okt

    jvmpath = config.resolve_jvm_path()
    return Okt(jvmpath=jvmpath) if jvmpath else Okt()


def normalize(text: str) -> str:
    """공백 정규화 등 가벼운 정제. (원문 보존이 필요한 분석을 위해 비파괴적)"""
    return _WS_RE.sub(" ", text).strip()


def _chunked(texts: Iterable[str], max_chars: int = 50_000) -> Iterator[str]:
    """다량의 발화를 큰 덩어리로 묶어 Okt 호출 횟수를 줄인다."""
    buf: list[str] = []
    size = 0
    for t in texts:
        t = normalize(t)
        if not t:
            continue
        if size + len(t) > max_chars and buf:
            yield "\n".join(buf)
            buf, size = [], 0
        buf.append(t)
        size += len(t)
    if buf:
        yield "\n".join(buf)


def noun_counts(texts: Iterable[str], min_len: int = 2) -> Counter[str]:
    """명사 빈도 Counter. 불용어 제거 + 최소 길이 필터(기본 2자 이상).

    2자 이상 기본값은 '자/것/수' 같은 1음절 노이즈를 1차로 걸러낸다.
    """
    okt = get_okt()
    counter: Counter[str] = Counter()
    for chunk in _chunked(texts):
        for noun in okt.nouns(chunk):
            if len(noun) >= min_len and noun not in config.STOPWORDS:
                counter[noun] += 1
    return counter


def filler_counts(texts: Iterable[str]) -> Counter[str]:
    """필러/군더더기 표현 빈도. 형태소 토큰이 필러 목록과 정확히 일치할 때 카운트.

    체크리스트 카테고리 1(언어 표현 품질 - 불필요한 반복 표현)의 정량 신호.
    """
    okt = get_okt()
    fillers = set(config.FILLER_WORDS)
    counter: Counter[str] = Counter()
    for chunk in _chunked(texts):
        for tok in okt.morphs(chunk):
            if tok in fillers:
                counter[tok] += 1
    return counter
