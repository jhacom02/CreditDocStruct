"""등급·전망 토큰 파싱 및 셀 내부 rating 토큰 개수 카운팅.

`extract/row_parser.py`가 셀당 rating 토큰 개수로 `rating_status`
(`none`/`single`/`ambiguous`)를 판정할 때 사용한다.

Plan: creditratefinder_restructure_43c68190 섹션 D/E 참고.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .text_utils import normalize_text

_RATING_VALUE_PATTERN = (
    r"(?:AAA|AA[+-]?|A1|A2[+-]?|A3[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|"
    r"CCC[+-]?|CC|C|D)"
)

_OUTLOOK_VALUE_PATTERN = (
    r"(?:Stable|Positive|Negative|Developing|안정적|긍정적|부정적|유동적)"
)

_OUTLOOK_MAP = {
    "stable": "Stable",
    "positive": "Positive",
    "negative": "Negative",
    "developing": "Developing",
    "안정적": "안정적",
    "긍정적": "긍정적",
    "부정적": "부정적",
    "유동적": "유동적",
}

RATING_TOKEN_RE = re.compile(
    rf"^(?P<rating>{_RATING_VALUE_PATTERN})"
    rf"(?P<sf>\(sf\))?"
    rf"(?:/(?P<outlook>{_OUTLOOK_VALUE_PATTERN}))?$",
    re.IGNORECASE,
)

OUTLOOK_TOKEN_RE = re.compile(
    rf"^(?P<outlook>{_OUTLOOK_VALUE_PATTERN})$",
    re.IGNORECASE,
)

RATING_SEARCH_RE = re.compile(
    rf"(?<![A-Z0-9])(?P<rating>{_RATING_VALUE_PATTERN})(?P<sf>\(sf\))?"
    rf"(?:\s*/\s*(?P<outlook>{_OUTLOOK_VALUE_PATTERN}))?(?![A-Z0-9+-])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RatingToken:
    rating: str
    outlook: str | None
    rating_display: str


def normalize_outlook(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_text(value)
    return _OUTLOOK_MAP.get(normalized.lower(), normalized)


def parse_rating_value(value: str | None) -> RatingToken | None:
    """단일 토큰 전체(예: `AA+/Stable`, `A+`)를 등급·전망으로 분해한다."""
    if not value:
        return None

    normalized = normalize_text(value).strip(" ,;:[]{}")
    match = RATING_TOKEN_RE.fullmatch(normalized)
    if not match:
        return None

    rating = match.group("rating").upper()
    if match.group("sf"):
        rating = f"{rating}(sf)"
    outlook = normalize_outlook(match.group("outlook"))
    rating_display = f"{rating}/{outlook}" if outlook else rating

    return RatingToken(
        rating=rating, outlook=outlook, rating_display=rating_display
    )


def find_rating_tokens_in_text(text: str | None) -> list[RatingToken]:
    """셀/문자열 내부에서 검출되는 모든 rating 토큰(등급[/전망])을 찾는다.

    한 셀 안에 토큰이 2개 이상이면 row_parser가 해당 행을 `ambiguous`로
    판정하는 근거가 된다.
    """
    if not text:
        return []

    normalized = normalize_text(text)
    tokens: list[RatingToken] = []

    for match in RATING_SEARCH_RE.finditer(normalized):
        rating = match.group("rating").upper()
        if match.group("sf"):
            rating = f"{rating}(sf)"
        outlook = normalize_outlook(match.group("outlook"))
        rating_display = f"{rating}/{outlook}" if outlook else rating
        tokens.append(
            RatingToken(
                rating=rating, outlook=outlook, rating_display=rating_display
            )
        )

    return tokens


def count_rating_tokens_in_cell(cell_text: str | None) -> int:
    """셀 하나에 포함된 rating 토큰 개수(모호성 판정의 기초 단위)."""
    return len(find_rating_tokens_in_text(cell_text))
