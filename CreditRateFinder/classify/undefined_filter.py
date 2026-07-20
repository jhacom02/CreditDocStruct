"""undefined_records 후보 필터링."""

from __future__ import annotations

import re

from common.models import RatingRecord

_EMAIL_RE = re.compile(r"[@\w.-]+@[\w.-]+\.\w+")
_PHONE_RE = re.compile(r"\d{2,4}[-\s]?\d{3,4}[-\s]?\d{4}")
_FINANCIAL_HINTS = (
    "bis",
    "총자산",
    "roa",
    "roe",
    "자기자본",
    "부채비율",
    "유동비율",
    "이자보상",
    "순이익",
    "매출액",
    "영업이익",
    "당기순이익",
    "재무지표",
    "주요재무",
    "등급추이",
)
_VALID_SECTIONS = frozenset({"primary_rating", "valid_ratings"})
_VALID_SOURCES = frozenset(
    {"pdf_table", "visual_layout", "valid_rating_section"}
)


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", (text or "")).lower()


def should_include_undefined_record(
    record: RatingRecord,
    *,
    primary_matched_labels: set[str] | None = None,
) -> bool:
    """admin/undefined 누적·undefined_records 출력에 포함할지 판단."""
    if record.classification_status != "undefined":
        return False

    if record.rating_status == "none" and not record.rating:
        return False

    section = record.section or ""
    source = record.source or ""
    if section not in _VALID_SECTIONS and source not in _VALID_SOURCES:
        return False

    normalized = record.normalized_label or ""
    if (
        primary_matched_labels
        and normalized
        and normalized in primary_matched_labels
        and source == "valid_rating_section"
    ):
        return False

    label = record.raw_label or normalized
    compact = _compact(label)

    if len(label) > 80:
        return False
    if _EMAIL_RE.search(label) or _PHONE_RE.search(label):
        return False
    if any(hint in compact for hint in _FINANCIAL_HINTS):
        return False

    return bool(label.strip())
