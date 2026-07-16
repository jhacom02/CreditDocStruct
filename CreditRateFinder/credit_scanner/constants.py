from __future__ import annotations

import re

EVALUATION_TYPES = {
    "본": 100,
    "본평가": 100,
    "신규": 95,
    "신규평가": 95,
    "예비": 90,
    "예비평가": 90,
    "수시": 80,
    "수시평가": 80,
    "정기": 70,
    "정기평가": 70,
}

RATING_ACTIONS = {
    "유지",
    "상향",
    "하향",
    "신규",
    "취소",
    "부여",
    "상향검토",
    "하향검토",
    "Watchlist",
}

OUTLOOK_MAP = {
    "stable": "Stable",
    "positive": "Positive",
    "negative": "Negative",
    "developing": "Developing",
    "안정적": "안정적",
    "긍정적": "긍정적",
    "부정적": "부정적",
    "유동적": "유동적",
}

RATING_VALUE_PATTERN = (
    r"(?:"
    r"AAA|"
    r"AA[+-]?|"
    r"A1|A2[+-]?|A3[+-]?|"
    r"A[+-]?|"
    r"BBB[+-]?|"
    r"BB[+-]?|"
    r"B[+-]?|"
    r"CCC[+-]?|"
    r"CC|C|D"
    r")"
)

OUTLOOK_VALUE_PATTERN = (
    r"(?:"
    r"Stable|Positive|Negative|Developing|"
    r"안정적|긍정적|부정적|유동적"
    r")"
)

RATING_TOKEN_RE = re.compile(
    rf"^(?P<rating>{RATING_VALUE_PATTERN})"
    rf"(?P<sf>\(sf\))?"
    rf"(?:/(?P<outlook>{OUTLOOK_VALUE_PATTERN}))?$",
    re.IGNORECASE,
)

OUTLOOK_TOKEN_RE = re.compile(
    rf"^(?P<outlook>{OUTLOOK_VALUE_PATTERN})$",
    re.IGNORECASE,
)

RATING_SEARCH_RE = re.compile(
    rf"(?<![A-Z0-9])"
    rf"(?P<rating>{RATING_VALUE_PATTERN})"
    rf"(?P<sf>\(sf\))?"
    rf"(?:\s*/\s*(?P<outlook>{OUTLOOK_VALUE_PATTERN}))?"
    rf"(?![A-Z0-9+-])",
    re.IGNORECASE,
)

HEADER_NOISE_TOKENS = (
    "평가대상",
    "구분",
    "종류",
    "현재등급",
    "직전등급",
    "ratingaction",
    "비고",
    "종목",
)

REMARK_CANDIDATES = (
    "상각형",
    "전환형",
    "영구상각형",
    "주식전환형",
    "원화 및 외화",
    "원화및외화",
)

TARGET_INSTRUMENT_CHOICES = (
    "coco_t1",
    "coco_t2",
    "coco",
    "coco_any",
    "issuer",
    "senior_unsecured",
    "subordinated",
    "commercial_paper",
    "short_term_bond",
    "insurance_payment",
    "structured_finance",
)
