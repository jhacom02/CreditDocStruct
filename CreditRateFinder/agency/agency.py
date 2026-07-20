"""신평사 식별 · 기관별 레이아웃 · 회사명 추출.

Plan: creditratefinder_restructure_43c68190 섹션 G 참고.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from common.text_utils import normalize_text


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


@dataclass(frozen=True)
class AgencyLayoutConfig:
    """기관별 표 헤더·섹션 경계 설정."""

    agency: str
    table_header_tokens: tuple[str, ...] = (
        "현재등급",
        "평가대상",
        "구분",
    )
    required_header_all: tuple[str, ...] = ("현재등급",)
    required_header_any: tuple[str, ...] = ("평가대상", "구분", "종류")
    primary_section_patterns: tuple[str, ...] = (
        r"평가\s*개요",
        r"평가\s*등급",
    )
    primary_end_patterns: tuple[str, ...] = (
        r"주요\s*재무\s*지표",
        r"등급\s*확정일",
        r"평가\s*담당자",
        r"주요\s*평가\s*요소",
        r"평가\s*근거",
        r"업체\s*개요",
        r"회사\s*개요",
    )
    valid_rating_patterns: tuple[str, ...] = (r"유효\s*등급",)
    valid_rating_end_patterns: tuple[str, ...] = (
        r"평가\s*등급\s*추이",
        r"등급\s*변동\s*추이",
        r"유사시\s*계열",
        r"계열\s*관계\s*요인",
        r"평가\s*담당자",
        r"주요\s*평가\s*요소",
    )
    valid_rating_width_ratio: float = 0.38
    valid_rating_max_width: float = 360.0
    extra_header_tokens: tuple[str, ...] = ()


NICE_LAYOUT = AgencyLayoutConfig(
    agency="NICE신용평가",
    primary_section_patterns=(
        r"평가\s*개요",
        r"평가\s*등급",
        r"Credit\s*Opinion",
    ),
    required_header_any=("평가대상", "구분", "종류", "Rating"),
    extra_header_tokens=("Rating Action", "Outlook"),
)

KIS_LAYOUT = AgencyLayoutConfig(
    agency="한국신용평가",
    primary_section_patterns=(
        r"평가\s*개요",
        r"평가\s*등급",
        r"신용\s*등급",
    ),
    primary_end_patterns=(
        r"주요\s*재무\s*지표",
        r"등급\s*확정일",
        r"평가\s*담당자",
        r"주요\s*평가\s*요소",
        r"평가\s*근거",
        r"업체\s*개요",
        r"회사\s*개요",
        r"등급\s*정의",
    ),
    required_header_any=("평가대상", "구분", "종류"),
)

KR_LAYOUT = AgencyLayoutConfig(
    agency="한국기업평가",
    primary_section_patterns=(
        r"평가\s*개요",
        r"평가\s*등급",
        r"등급\s*요약",
    ),
    required_header_any=("평가대상", "구분", "종류", "종목"),
    valid_rating_width_ratio=0.42,
    valid_rating_max_width=380.0,
)

DEFAULT_LAYOUT = AgencyLayoutConfig(agency="미확인")

_LAYOUT_BY_AGENCY: dict[str, AgencyLayoutConfig] = {
    NICE_LAYOUT.agency: NICE_LAYOUT,
    KIS_LAYOUT.agency: KIS_LAYOUT,
    KR_LAYOUT.agency: KR_LAYOUT,
}


def get_agency_layout(agency: str | None) -> AgencyLayoutConfig:
    if not agency:
        return DEFAULT_LAYOUT
    return _LAYOUT_BY_AGENCY.get(agency, DEFAULT_LAYOUT)


def is_rating_table_header(
    compact_header_text: str,
    layout: AgencyLayoutConfig,
) -> bool:
    text = compact_header_text.lower()

    if not all(token.lower() in text for token in layout.required_header_all):
        return False

    if not any(token.lower() in text for token in layout.required_header_any):
        return False

    return True


def detect_agency(text: str) -> str:
    compact = _compact(text)

    if "nicecreditopinion" in compact or "nice신용평가" in compact:
        return "NICE신용평가"

    if "kiscreditopinion" in compact or "한국신용평가" in compact:
        return "한국신용평가"

    if (
        "한국기업평가" in compact
        or "korearatings" in compact
        or "krcredit" in compact
    ):
        return "한국기업평가"

    return "미확인"


_COMPANY_NOISE = (
    "credit opinion",
    "신용평가",
    "신용등급",
    "평가개요",
    "평가등급",
    "nice",
    "kis",
    "한국기업평가",
    "한국신용평가",
    "nice신용평가",
)


def extract_company_name(
    page_text: str,
    file_name: str | Path,
) -> str:
    """1페이지 헤더/제목에서 회사명 추출. 실패 시 파일명 stem 보조."""
    lines = [
        normalize_text(line)
        for line in (page_text or "").splitlines()
        if normalize_text(line)
    ]

    for line in lines[:12]:
        compact = _compact(line)
        if len(line) < 2 or len(line) > 60:
            continue
        if any(noise in compact for noise in _COMPANY_NOISE):
            continue
        if re.fullmatch(r"[\d\W]+", line):
            continue
        # 등급 토큰만 있는 줄 제외
        if re.fullmatch(
            r"(?:AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC?|CC|C|D)"
            r"(?:/(?:Stable|Positive|Negative|Developing|안정적|긍정적|부정적|유동적))?",
            line,
            re.IGNORECASE,
        ):
            continue
        return line

    stem = Path(file_name).stem
    stem = re.sub(
        r"[_-]?(NICE|KIS|KR|신용평가|신용등급|CreditOpinion).*$",
        "",
        stem,
        flags=re.IGNORECASE,
    )
    stem = stem.replace("_", " ").replace("-", " ").strip()
    return stem or Path(file_name).stem
