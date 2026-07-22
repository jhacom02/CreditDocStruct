"""ExtractedTableGrid → ExtractedRatingRow (등급 L3 입력)."""

from __future__ import annotations

import re

from common.models import ExtractedRatingRow, ExtractedTableGrid
from common.rating_tokens import RATING_SEARCH_RE, find_rating_tokens_in_text
from common.text_utils import normalize_text
from extract.row_parser import (
    looks_like_instrument_label,
    parse_rating_row_values,
    truncate_valid_row_text,
)
from extract.section_catalog import SECTION_PRIMARY, SECTION_VALID

# 라벨 자체가 재무지표인 경우만 행 전체 폐기
_METRIC_LABEL_RE = re.compile(
    r"(?:"
    r"ROA|ROE|NIM|BIS|Peer|PEER|EBITDA|EBIT"
    r"|충당금|고정이하|요주의|자기자본비율|총자산증가"
    r"|이익률|연체율|레버리지|유동성비율|부채비율"
    r"|적용재무제표"
    r")",
    re.IGNORECASE,
)
_DECIMAL_TOKEN_RE = re.compile(r"\d+\.\d+")
_NA_ONLY_RE = re.compile(r"^[\sN/A\.na\-—]*$", re.IGNORECASE)


def is_rating_tokens_only_label(label: str | None) -> bool:
    """라벨이 상품명 없이 등급 토큰만 나열된 경우 (예: 'A+ A A-')."""
    normalized = normalize_text(label)
    if not normalized or looks_like_instrument_label(normalized):
        return False
    tokens = find_rating_tokens_in_text(normalized)
    if not tokens:
        return False
    remainder = normalized
    for match in RATING_SEARCH_RE.finditer(normalized):
        remainder = remainder.replace(match.group(0), " ")
    remainder = re.sub(r"[\s/\-+·,;:]", "", remainder)
    return not remainder


def _clean_row_values(values: list) -> list[str]:
    """등급 셀에 붙은 재무 시계열을 truncate."""
    cleaned: list[str] = []
    for index, cell in enumerate(values):
        text = "" if cell is None else str(cell)
        if index == 0:
            cleaned.append(text)
        else:
            cleaned.append(truncate_valid_row_text(text) or text)
    return cleaned


def is_financial_noise_rating_row(values: list) -> bool:
    """라벨이 재무지표이거나, 등급 없이 시계열만 있으면 True."""
    if not values:
        return True
    label = normalize_text(str(values[0] or ""))
    if not label:
        return True

    if is_rating_tokens_only_label(label):
        return True

    # 상품 라벨처럼 보이면 행 유지(셀 트림으로 처리)
    if looks_like_instrument_label(label):
        return False

    if _METRIC_LABEL_RE.search(label):
        return True

    text = normalize_text(" ".join(str(cell or "") for cell in values))
    decimals = _DECIMAL_TOKEN_RE.findall(text)
    tokens = find_rating_tokens_in_text(text)
    rating_cells = [str(cell or "").strip() for cell in values[1:]]
    na_only = rating_cells and all(
        (not cell)
        or _NA_ONLY_RE.match(cell)
        or cell.upper() in {"N.A", "N.A.", "NA", "-"}
        for cell in rating_cells
    )
    if na_only and (decimals or _METRIC_LABEL_RE.search(text)):
        return True
    if len(decimals) >= 3 and not tokens:
        return True
    return False


def rating_rows_from_grid(
    grid: ExtractedTableGrid,
) -> list[ExtractedRatingRow]:
    """공용 그리드를 기존 등급 파서 입력으로 변환한다."""
    if grid.section_key == SECTION_PRIMARY:
        section = "primary_rating"
        source = (
            "pdf_table" if grid.source == "pdf_table" else "visual_layout"
        )
    elif grid.section_key == SECTION_VALID:
        section = "valid_ratings"
        source = "valid_rating_section"
    else:
        return []

    records: list[ExtractedRatingRow] = []
    header_cells = list(grid.headers) if grid.headers else None
    row_index = 0
    for values in grid.rows:
        if not any(str(cell).strip() for cell in values):
            continue
        if is_financial_noise_rating_row(list(values)):
            continue

        cleaned = _clean_row_values(list(values))
        current_cell = None
        if grid.section_key == SECTION_VALID and len(cleaned) >= 2:
            current_cell = cleaned[1] or None

        record = parse_rating_row_values(
            values=cleaned,
            page_number=grid.page,
            row_index=row_index,
            section=section,
            source=source,
            header_cells=header_cells,
            current_rating_cell=current_cell,
        )
        if record is None:
            continue
        if (
            grid.section_key == SECTION_VALID
            and record.rating_status == "none"
            and not record.rating
        ):
            continue
        if record.rating and str(record.rating).upper() in {
            "N.A",
            "N.A.",
            "NA",
        }:
            continue
        records.append(record)
        row_index += 1
    return records


def rating_rows_from_section_tables(
    section_tables: dict[str, ExtractedTableGrid | None] | dict[str, list],
) -> list[ExtractedRatingRow]:
    """section 결과에서 primary+valid 등급 행만 모은다."""
    rows: list[ExtractedRatingRow] = []
    for key in (SECTION_PRIMARY, SECTION_VALID):
        value = section_tables.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            for grid in value:
                rows.extend(rating_rows_from_grid(grid))
        else:
            rows.extend(rating_rows_from_grid(value))
    return rows
