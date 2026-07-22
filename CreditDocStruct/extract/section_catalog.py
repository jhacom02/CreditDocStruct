"""표 섹션 카탈로그 — 제목 3종만 추출 대상."""

from __future__ import annotations

import re
from dataclasses import dataclass

from common.text_utils import normalize_text

SECTION_PRIMARY = "primary_rating"
SECTION_VALID = "valid_rating"
SECTION_FINANCIAL = "financial_indicators"

SECTION_KEYS = (SECTION_PRIMARY, SECTION_VALID, SECTION_FINANCIAL)


@dataclass(frozen=True)
class SectionSpec:
    section_key: str
    title_aliases: tuple[str, ...]
    title_patterns: tuple[str, ...]
    end_patterns: tuple[str, ...]


SECTION_CATALOG: dict[str, SectionSpec] = {
    SECTION_PRIMARY: SectionSpec(
        section_key=SECTION_PRIMARY,
        title_aliases=(
            "평가개요",
            "평가 개요",
            "평가등급",
            "평가 등급",
        ),
        title_patterns=(
            r"평가\s*개요",
            r"평가\s*등급",
        ),
        end_patterns=(
            r"주요\s*재무\s*지표",
            r"등급\s*확정일",
            r"평가\s*담당자",
            r"주요\s*평가\s*요소",
            r"평가\s*근거",
            r"업체\s*개요",
            r"회사\s*개요",
            r"등급\s*정의",
        ),
    ),
    SECTION_VALID: SectionSpec(
        section_key=SECTION_VALID,
        title_aliases=("유효등급", "유효 등급"),
        title_patterns=(r"유효\s*등급",),
        end_patterns=(
            r"평가\s*등급\s*추이",
            r"등급\s*변동\s*추이",
            r"유사시\s*계열",
            r"계열\s*관계\s*요인",
            r"평가\s*담당자",
            r"주요\s*평가\s*요소",
        ),
    ),
    SECTION_FINANCIAL: SectionSpec(
        section_key=SECTION_FINANCIAL,
        title_aliases=("주요 재무지표", "주요 재무 지표"),
        title_patterns=(r"주요\s*재무\s*지표",),
        end_patterns=(
            r"평정\s*논거",
            r"자료\s*[:：]",
            r"등급\s*정의",
            r"평가\s*담당자",
            r"주요\s*평가\s*요소",
            r"업체\s*개요",
            r"회사\s*개요",
        ),
    ),
}


def compact_title(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


def match_section_key(text: str | None) -> str | None:
    """줄 텍스트가 카탈로그 제목이면 section_key, 아니면 None."""
    normalized = normalize_text(text)
    compact = compact_title(normalized)
    if not compact:
        return None

    for key, spec in SECTION_CATALOG.items():
        alias_compacts = {compact_title(alias) for alias in spec.title_aliases}
        if compact in alias_compacts:
            return key
        # 제목 줄이 alias로 시작하거나 동일 계열
        for alias_c in alias_compacts:
            if compact == alias_c or compact.startswith(alias_c):
                if len(compact) <= len(alias_c) + 4:
                    return key
        for pattern in spec.title_patterns:
            if re.fullmatch(pattern, normalized, re.IGNORECASE):
                return key
            if (
                len(compact) <= 14
                and re.search(pattern, normalized, re.IGNORECASE)
            ):
                return key
    return None


def title_patterns_for(section_key: str) -> tuple[str, ...]:
    return SECTION_CATALOG[section_key].title_patterns


def end_patterns_for(section_key: str) -> tuple[str, ...]:
    return SECTION_CATALOG[section_key].end_patterns
