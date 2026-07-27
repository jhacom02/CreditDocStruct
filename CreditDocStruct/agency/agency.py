"""신평사 식별 · 기관별 레이아웃 · 회사명 추출.

Plan: CreditDocStruct_restructure_43c68190 섹션 G 참고.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from common.text_utils import normalize_text


AGENCY_KEYS = ("nice", "kis", "kr")

AGENCY_DISPLAY_NAMES: dict[str, str] = {
    "nice": "NICE신용평가㈜",
    "kis": "한국신용평가㈜",
    "kr": "한국기업평가㈜",
}

_LEGACY_AGENCY_ALIASES: dict[str, str] = {
    "nice신용평가": "nice",
    "nice신용평가㈜": "nice",
    "한국신용평가": "kis",
    "한국신용평가㈜": "kis",
    "한국기업평가": "kr",
    "한국기업평가㈜": "kr",
    "미확인": "kis",
}


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


def normalize_agency_key(agency: str | None) -> str | None:
    if not agency:
        return None
    compact = _compact(agency)
    if compact in AGENCY_DISPLAY_NAMES:
        return compact
    if compact in _LEGACY_AGENCY_ALIASES:
        return _LEGACY_AGENCY_ALIASES[compact]
    for key, display in AGENCY_DISPLAY_NAMES.items():
        if _compact(display) == compact:
            return key
    return None


def format_agency_display(agency_key: str | None) -> str:
    if agency_key and agency_key in AGENCY_DISPLAY_NAMES:
        return AGENCY_DISPLAY_NAMES[agency_key]
    return AGENCY_DISPLAY_NAMES["kis"]


@dataclass(frozen=True)
class AgencyLayoutConfig:
    """기관별 표 헤더·섹션 경계 설정."""

    agency_key: str
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
    # 거터 실패 시 최후 fallback 전용 (공용 region 경로가 우선)
    valid_rating_width_ratio: float = 0.38
    valid_rating_max_width: float = 360.0
    extra_header_tokens: tuple[str, ...] = ()

    @property
    def agency(self) -> str:
        return format_agency_display(self.agency_key)


NICE_LAYOUT = AgencyLayoutConfig(
    agency_key="nice",
    primary_section_patterns=(
        r"평가\s*개요",
        r"평가\s*등급",
        r"Credit\s*Opinion",
    ),
    required_header_any=("평가대상", "구분", "종류", "Rating"),
    extra_header_tokens=("Rating Action", "Outlook"),
)

KIS_LAYOUT = AgencyLayoutConfig(
    agency_key="kis",
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
    agency_key="kr",
    primary_section_patterns=(
        r"평가\s*개요",
        r"평가\s*등급",
        r"등급\s*요약",
    ),
    required_header_any=("평가대상", "구분", "종류", "종목"),
    valid_rating_width_ratio=0.42,
    valid_rating_max_width=380.0,
)

DEFAULT_LAYOUT = AgencyLayoutConfig(agency_key="kis")

_LAYOUT_BY_KEY: dict[str, AgencyLayoutConfig] = {
    "nice": NICE_LAYOUT,
    "kis": KIS_LAYOUT,
    "kr": KR_LAYOUT,
}


def get_agency_layout(agency: str | None) -> AgencyLayoutConfig:
    key = normalize_agency_key(agency)
    if not key:
        return DEFAULT_LAYOUT
    return _LAYOUT_BY_KEY.get(key, DEFAULT_LAYOUT)


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


def detect_agency_key(text: str) -> str | None:
    compact = _compact(text)

    if "nicecreditopinion" in compact or "nice신용평가" in compact:
        return "nice"

    if "kiscreditopinion" in compact or "한국신용평가" in compact:
        return "kis"

    if (
        "한국기업평가" in compact
        or "korearatings" in compact
        or "krcredit" in compact
    ):
        return "kr"

    return None


def detect_agency_key_from_filename(file_name: str | Path) -> str | None:
    stem = _compact(Path(file_name).stem)
    if not stem:
        return None

    if "nice" in stem or "나이스" in stem:
        return "nice"
    if "korearatings" in stem or "kr" in stem or "한기평" in stem:
        return "kr"
    if (
        "kis" in stem
        or "한신평" in stem
        or "한국신용" in stem
        or re.search(r"(?<![a-z])rs(?![a-z])", stem)
    ):
        return "kis"

    return None


def resolve_agency_key(
    text: str,
    file_name: str | Path,
) -> str:
    key = detect_agency_key(text)
    if key:
        return key
    filename_key = detect_agency_key_from_filename(file_name)
    if filename_key:
        return filename_key
    return "kis"


def detect_agency(text: str) -> str:
    """외부 출력용 신평사 표준명 (㈜ 포함)."""
    return format_agency_display(detect_agency_key(text))


_COMPANY_NOISE = (
    "credit opinion",
    "nice credit opinion",
    "kis credit opinion",
    "신용평가",
    "신용등급",
    "평가개요",
    "평가등급",
    "등급요약",
    "nice",
    "kis",
    "korearatings",
    "한국기업평가",
    "한국신용평가",
    "nice신용평가",
    "nice신용평가㈜",
    "한국신용평가㈜",
    "한국기업평가㈜",
)

# 회사명 출력 시 제거 (탐지 시 '(주)' 포함 여부와 별개)
_COMPANY_CORP_MARK_RE = re.compile(r"\(\s*주\s*\)|㈜")


def is_plausible_company_name(value: str) -> bool:
    line = normalize_text(value)
    if len(line) < 2 or len(line) > 60:
        return False

    compact = _compact(line)
    if any(noise in compact for noise in _COMPANY_NOISE):
        return False
    if re.fullmatch(r"[\d\W]+", line):
        return False
    if re.fullmatch(
        r"(?:AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC?|CC|C|D)"
        r"(?:/(?:Stable|Positive|Negative|Developing|안정적|긍정적|부정적|유동적))?",
        line,
        re.IGNORECASE,
    ):
        return False

    if "(주)" in line or "(유)" in line or re.search(r"[가-힣]{2,}", line):
        return True
    return False


def _clean_company_name(value: str) -> str:
    """추출 회사명에서 (주)·㈜ 표기 제거."""
    cleaned = _COMPANY_CORP_MARK_RE.sub("", normalize_text(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or normalize_text(value)


def _company_name_from_filename(file_name: str | Path) -> str:
    stem = Path(file_name).stem
    stem = re.sub(
        r"[_-]?(NICE|KIS|KR|신용평가|신용등급|CreditOpinion).*$",
        "",
        stem,
        flags=re.IGNORECASE,
    )
    stem = stem.replace("_", " ").replace("-", " ").strip()
    return _clean_company_name(stem or Path(file_name).stem)


def extract_company_name(
    page: pymupdf.Page | str,
    file_name: str | Path,
    *,
    agency_key: str | None = None,
) -> str:
    """제목 영역에서 평가대상 회사명 추출. 실패 시 파일명 stem 보조."""
    if isinstance(page, str):
        page_text = page
        lines = [
            normalize_text(line)
            for line in (page_text or "").splitlines()
            if normalize_text(line)
        ]
        for line in lines[:12]:
            if is_plausible_company_name(line):
                return _clean_company_name(line)
        return _company_name_from_filename(file_name)

    layout = get_agency_layout(agency_key)
    from extract.visual import extract_visual_lines, find_heading_line

    all_lines = extract_visual_lines(page)
    heading = find_heading_line(all_lines, layout.primary_section_patterns)

    title_lines: list[str] = []
    if heading:
        title_lines = [
            line.text
            for line in all_lines
            if line.y1 <= heading.y0 + 2
        ]
    if not title_lines:
        title_lines = [line.text for line in all_lines[:12]]

    for line in title_lines:
        if is_plausible_company_name(line):
            return _clean_company_name(line)

    page_text = page.get_text("text", sort=True)
    for line in page_text.splitlines():
        normalized = normalize_text(line)
        if is_plausible_company_name(normalized):
            return _clean_company_name(normalized)

    return _company_name_from_filename(file_name)
