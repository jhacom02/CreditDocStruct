"""등급·전망 토큰 파싱 및 셀 내부 rating 토큰 개수 카운팅."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .text_utils import normalize_text

_RATING_VALUE_PATTERN = (
    r"(?:AAA|AA[+-]?|A1|A2[+-]?|A3[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?)"
)

_OUTLOOK_VALUE_PATTERN = (
    r"(?:Stable|Positive|Negative|Developing|안정적|긍정적|부정적|유동적)"
)

_OUTLOOK_SHORT_PATTERN = r"S|P|N|D"

_OUTLOOK_MAP = {
    "stable": "안정적",
    "positive": "긍정적",
    "negative": "부정적",
    "developing": "유동적",
    "s": "안정적",
    "p": "긍정적",
    "n": "부정적",
    "d": "유동적",
    "안정적": "안정적",
    "긍정적": "긍정적",
    "부정적": "부정적",
    "유동적": "유동적",
}

RATING_TOKEN_RE = re.compile(
    rf"^(?P<rating>{_RATING_VALUE_PATTERN})"
    rf"(?P<sf>\(sf\))?"
    rf"(?:/(?P<outlook_slash>{_OUTLOOK_VALUE_PATTERN}))?"
    rf"(?:\((?P<outlook_paren>{_OUTLOOK_VALUE_PATTERN}|{_OUTLOOK_SHORT_PATTERN})\))?$",
    re.IGNORECASE,
)

OUTLOOK_TOKEN_RE = re.compile(
    rf"^(?P<outlook>{_OUTLOOK_VALUE_PATTERN}|{_OUTLOOK_SHORT_PATTERN})$",
    re.IGNORECASE,
)

_RATING_BOUNDARY_BEFORE = r"(?<![A-Z0-9가-힣])"
_RATING_BOUNDARY_AFTER = r"(?![A-Z0-9가-힣])"

RATING_SEARCH_RE = re.compile(
    rf"{_RATING_BOUNDARY_BEFORE}(?P<rating>{_RATING_VALUE_PATTERN})(?P<sf>\(sf\))?"
    rf"(?:\s*/\s*(?P<outlook_slash>{_OUTLOOK_VALUE_PATTERN}))?"
    rf"(?:\s*\((?P<outlook_paren>{_OUTLOOK_VALUE_PATTERN}|{_OUTLOOK_SHORT_PATTERN})\))?"
    rf"{_RATING_BOUNDARY_AFTER}",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RatingToken:
    rating: str
    outlook: str | None
    rating_display: str
    raw_outlook: str | None = None


def normalize_outlook(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_text(value).strip("()")
    return _OUTLOOK_MAP.get(normalized.lower(), normalized)


def _build_token(
    rating: str,
    *,
    sf: str | None,
    outlook_slash: str | None,
    outlook_paren: str | None,
) -> RatingToken:
    if sf:
        rating = f"{rating}(sf)"
    raw_outlook = outlook_slash or outlook_paren
    if raw_outlook and not outlook_slash and outlook_paren:
        raw_outlook = f"({outlook_paren})"
    elif raw_outlook and outlook_slash:
        raw_outlook = outlook_slash
    outlook = normalize_outlook(raw_outlook)
    rating_display = f"{rating}/{outlook}" if outlook else rating
    return RatingToken(
        rating=rating,
        outlook=outlook,
        rating_display=rating_display,
        raw_outlook=raw_outlook,
    )


def parse_rating_value(value: str | None) -> RatingToken | None:
    if not value:
        return None

    normalized = normalize_text(value).strip(" ,;:[]{}")
    match = RATING_TOKEN_RE.fullmatch(normalized)
    if not match:
        return None

    rating = match.group("rating").upper()
    return _build_token(
        rating,
        sf=match.group("sf"),
        outlook_slash=match.group("outlook_slash"),
        outlook_paren=match.group("outlook_paren"),
    )


def find_rating_tokens_in_text(text: str | None) -> list[RatingToken]:
    if not text:
        return []

    normalized = normalize_text(text)
    tokens: list[RatingToken] = []

    for match in RATING_SEARCH_RE.finditer(normalized):
        rating = match.group("rating").upper()
        if match.group("sf"):
            rating = f"{rating}(sf)"
        end_pos = match.end("rating")
        if end_pos < len(normalized):
            next_char = normalized[end_pos]
            if next_char == "-" and end_pos + 1 < len(normalized):
                if normalized[end_pos + 1].isdigit():
                    continue
            if (
                len(rating) == 1
                and rating in {"A", "B"}
                and next_char == "-"
                and end_pos + 1 < len(normalized)
                and normalized[end_pos + 1].isdigit()
            ):
                continue
        tokens.append(
            _build_token(
                rating,
                sf=match.group("sf"),
                outlook_slash=match.group("outlook_slash"),
                outlook_paren=match.group("outlook_paren"),
            )
        )

    return tokens


def count_rating_tokens_in_cell(cell_text: str | None) -> int:
    return len(find_rating_tokens_in_text(cell_text))
