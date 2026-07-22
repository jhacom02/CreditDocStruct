"""평가개요·유효등급 영역에서 ExtractedRatingRow 추출."""

from __future__ import annotations

import re

import pymupdf

from agency.agency import get_agency_layout
from common.models import ExtractedRatingRow
from common.rating_tokens import find_rating_tokens_in_text
from common.text_utils import normalize_text
from extract.row_parser import (
    CURRENT_RATING_HEADER_NAMES,
    looks_like_instrument_label,
    looks_like_rating_row,
    parse_rating_row_values,
)
from extract.visual import (
    column_x_range_for_token,
    extract_visual_lines,
    find_header_token_spans,
    find_heading_line,
    text_in_x_range,
)

_VALID_NOISE_PATTERNS = (
    r"BIS\s*자본",
    r"BIS자본",
    r"ROA\s*\(",
    r"ROA\(",
    r"ROE\s*\(",
    r"총자산",
    r"등급\s*추이",
    r"자기자본",
    r"부채비율",
    r"Peer",
)


def truncate_valid_row_text(text: str) -> str:
    """유효등급 행에서 재무지표·등급추이 등 노이즈 이전까지만 유지."""
    normalized = normalize_text(text)
    if not normalized:
        return ""

    cut_index = len(normalized)
    for pattern in _VALID_NOISE_PATTERNS:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            cut_index = min(cut_index, match.start())

    trimmed = normalize_text(normalized[:cut_index])
    if not trimmed:
        return normalized

    if find_rating_tokens_in_text(trimmed):
        return trimmed

    return normalized


def extract_primary_rows_from_visual_layout(
    page: pymupdf.Page,
    agency: str,
) -> list[ExtractedRatingRow]:
    layout = get_agency_layout(agency)
    all_lines = extract_visual_lines(page)

    heading = find_heading_line(all_lines, layout.primary_section_patterns)
    if not heading:
        return []

    end_y = page.rect.height

    for line in all_lines:
        if line.y0 <= heading.y1 + 5:
            continue

        if any(
            re.search(pattern, normalize_text(line.text), re.IGNORECASE)
            for pattern in layout.primary_end_patterns
        ):
            end_y = min(end_y, line.y0)

    clip = pymupdf.Rect(
        max(0, heading.x0 - 10),
        heading.y1,
        page.rect.width,
        end_y,
    )
    section_lines = extract_visual_lines(page, clip=clip)

    header_tokens = (
        "평가대상",
        "구분",
        "종류",
        "종목",
        "현재등급",
        "직전등급",
        "Rating Action",
        "비고",
    )
    spans = find_header_token_spans(page, clip, header_tokens)
    current_range = None
    for name in CURRENT_RATING_HEADER_NAMES:
        current_range = column_x_range_for_token(
            spans, name, page.rect.width
        )
        if current_range is not None:
            break

    header_cells: list[str] | None = None
    if spans:
        header_cells = [name for name, _x0, _x1, _ymid in spans]

    records: list[ExtractedRatingRow] = []
    row_index = 0

    for index, line in enumerate(section_lines):
        if not looks_like_rating_row(line.text):
            continue

        if (
            find_rating_tokens_in_text(line.text)
            and not looks_like_instrument_label(line.text)
            and len(normalize_text(line.text)) < 12
        ):
            continue

        if "@" in normalize_text(line.text):
            continue

        compact_line = re.sub(r"\s+", "", normalize_text(line.text)).lower()
        if "현재등급" in compact_line and "직전" in compact_line:
            continue

        row_parts = [line.text]

        for offset in range(1, 4):
            next_index = index + offset
            if next_index >= len(section_lines):
                break

            next_line = section_lines[next_index]

            if looks_like_rating_row(next_line.text) and (
                looks_like_instrument_label(next_line.text)
            ):
                break

            if next_line.y0 - line.y1 > 45:
                break

            row_parts.append(next_line.text)
            if find_rating_tokens_in_text(" ".join(row_parts)):
                break

        current_cell: str | None = None
        if current_range is not None:
            x0, x1 = current_range
            current_cell = text_in_x_range(
                page,
                y0=line.y0 - 2,
                y1=line.y1 + 2,
                x0=x0,
                x1=x1,
            ) or None

        record = parse_rating_row_values(
            values=row_parts,
            page_number=page.number + 1,
            row_index=row_index,
            section="primary_rating",
            source="visual_layout",
            header_cells=header_cells,
            current_rating_cell=current_cell,
        )
        if record:
            records.append(record)
            row_index += 1

    return records


def extract_valid_rating_rows(
    page: pymupdf.Page,
    agency: str,
) -> list[ExtractedRatingRow]:
    """유효등급 섹션 추출 — region clip 기반 (고정폭 clip 폐기)."""
    from extract.rating_from_grid import rating_rows_from_grid
    from extract.section_catalog import SECTION_VALID
    from extract.sections import extract_section_tables

    del agency
    section_tables = extract_section_tables(page)
    grid = section_tables.get(SECTION_VALID)
    if grid is None:
        return []
    return rating_rows_from_grid(grid)
