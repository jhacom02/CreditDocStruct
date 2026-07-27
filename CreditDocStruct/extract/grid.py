"""region clip 안 공용 표 그리드 복원 (find_tables → visual_grid)."""

from __future__ import annotations

import re
from typing import Any

import pymupdf

from common.models import ExtractedTableGrid, VisualLine
from common.rating_tokens import find_rating_tokens_in_text
from common.text_utils import normalize_text
from extract.fin_tables import (
    _detect_basis,
    _detect_unit_caption,
    _extract_footnotes,
    _header_row_index,
    filter_financial_data_rows,
    parse_period_header,
)
from extract.section_catalog import SECTION_FINANCIAL, SECTION_PRIMARY, SECTION_VALID
from extract.visual import (
    column_x_range_for_token,
    extract_visual_lines,
    find_header_token_spans,
    text_in_x_range,
)

PRIMARY_HEADER_TOKENS = (
    "평가대상",
    "구분",
    "종류",
    "종목",
    "현재등급",
    "직전등급",
    "비고",
    "Rating",
    "Outlook",
)


def _clean_matrix(matrix: list[list[Any]]) -> list[list[str]]:
    return [
        [normalize_text(cell) if cell is not None else "" for cell in row]
        for row in matrix
    ]


def _bbox_tuple(table: object) -> tuple[float, float, float, float] | None:
    raw = getattr(table, "bbox", None)
    if not raw:
        return None
    try:
        rect = pymupdf.Rect(raw)
        return (rect.x0, rect.y0, rect.x1, rect.y1)
    except Exception:
        return None


def _is_primary_header_row(row: list[str]) -> bool:
    compact = re.sub(r"\s+", "", "".join(row)).lower()
    has_rating = "현재등급" in compact or "currentrating" in compact
    has_target = any(
        token in compact for token in ("평가대상", "구분", "종류", "종목", "rating")
    )
    return has_rating and has_target


def _grid_from_table_matrix(
    cleaned: list[list[str]],
    *,
    section_key: str,
    title_raw: str,
    page: int,
    region_id: str,
    source: str,
    bbox: tuple[float, float, float, float] | None,
    basis: str | None = None,
    unit_caption: str | None = None,
) -> ExtractedTableGrid | None:
    if section_key == SECTION_FINANCIAL:
        header_index = _header_row_index(cleaned)
        if header_index is None:
            return None
        headers = list(cleaned[header_index])
        rows = [
            list(row)
            for row in cleaned[header_index + 1 :]
            if any(cell.strip() for cell in row)
        ]
        rows = filter_financial_data_rows(rows)
        if not rows:
            return None
        if header_index > 0:
            basis = basis or _detect_basis(
                [" ".join(row) for row in cleaned[:header_index]]
            )
        return ExtractedTableGrid(
            section_key=section_key,
            title_raw=title_raw,
            page=page,
            headers=headers,
            rows=rows,
            region_id=region_id,
            source=source,
            basis=basis,
            unit_caption=unit_caption,
            bbox=bbox,
        )

    if section_key == SECTION_PRIMARY:
        header_index = None
        for index, row in enumerate(cleaned[:8]):
            if _is_primary_header_row(row):
                header_index = index
                break
        if header_index is None:
            return None
        headers = list(cleaned[header_index])
        rows = [
            list(row)
            for row in cleaned[header_index + 1 :]
            if any(cell.strip() for cell in row)
        ]
        if not rows:
            return None
        return ExtractedTableGrid(
            section_key=section_key,
            title_raw=title_raw,
            page=page,
            headers=headers,
            rows=rows,
            region_id=region_id,
            source=source,
            bbox=bbox,
        )

    rows = [list(row) for row in cleaned if any(cell.strip() for cell in row)]
    if not rows:
        return None
    filtered: list[list[str]] = []
    for row in rows:
        joined = normalize_text(" ".join(row))
        if re.search(r"유효\s*등급", joined, re.IGNORECASE):
            continue
        filtered.append(row)
    if not filtered:
        return None
    col_count = max(len(row) for row in filtered)
    headers = [f"col_{i}" for i in range(col_count)]
    if col_count >= 2:
        headers = ["구분", "등급"] + [f"col_{i}" for i in range(2, col_count)]
    aligned = []
    for row in filtered:
        padded = list(row[:col_count]) + [""] * max(0, col_count - len(row))
        aligned.append(padded)
    return ExtractedTableGrid(
        section_key=section_key,
        title_raw=title_raw,
        page=page,
        headers=headers,
        rows=aligned,
        region_id=region_id,
        source=source,
        bbox=bbox,
    )


def _extract_via_find_tables(
    page: pymupdf.Page,
    clip: pymupdf.Rect,
    *,
    section_key: str,
    title_raw: str,
    region_id: str,
    basis: str | None,
    unit_caption: str | None,
) -> ExtractedTableGrid | None:
    try:
        finder = page.find_tables(clip=clip)
        tables = list(finder.tables)
    except Exception:
        return None

    for table in tables:
        try:
            matrix = table.extract()
        except Exception:
            continue
        if not matrix:
            continue
        cleaned = _clean_matrix(matrix)
        grid = _grid_from_table_matrix(
            cleaned,
            section_key=section_key,
            title_raw=title_raw,
            page=page.number + 1,
            region_id=region_id,
            source="pdf_table",
            bbox=_bbox_tuple(table),
            basis=basis,
            unit_caption=unit_caption,
        )
        if grid is not None:
            return grid
    return None


def _visual_primary_grid(
    page: pymupdf.Page,
    clip: pymupdf.Rect,
    *,
    title_raw: str,
    region_id: str,
) -> ExtractedTableGrid | None:
    spans = find_header_token_spans(page, clip, PRIMARY_HEADER_TOKENS)
    if len(spans) < 2:
        return None

    headers = [name for name, _x0, _x1, _ymid in spans]
    col_ranges: list[tuple[float, float]] = []
    for name, _x0, _x1, _ymid in spans:
        rng = column_x_range_for_token(spans, name, page.rect.width)
        if rng is None:
            return None
        col_ranges.append(rng)

    header_y = spans[0][3]
    lines = extract_visual_lines(page, clip=clip)
    rows: list[list[str]] = []
    for line in lines:
        if line.y0 <= header_y + 6:
            continue
        compact = re.sub(r"\s+", "", normalize_text(line.text)).lower()
        if "현재등급" in compact and "직전" in compact:
            continue
        cells = [
            text_in_x_range(
                page,
                y0=line.y0 - 1,
                y1=line.y1 + 1,
                x0=x0,
                x1=x1,
            )
            for x0, x1 in col_ranges
        ]
        if any(cells):
            rows.append(cells)
    if not rows:
        return None
    return ExtractedTableGrid(
        section_key=SECTION_PRIMARY,
        title_raw=title_raw,
        page=page.number + 1,
        headers=headers,
        rows=rows,
        region_id=region_id,
        source="visual_grid",
        bbox=(clip.x0, clip.y0, clip.x1, clip.y1),
    )


def _visual_valid_grid(
    page: pymupdf.Page,
    clip: pymupdf.Rect,
    *,
    title_raw: str,
    region_id: str,
) -> ExtractedTableGrid | None:
    lines = extract_visual_lines(page, clip=clip)
    rows: list[list[str]] = []
    for line in lines:
        text = normalize_text(line.text)
        if not text:
            continue
        if re.search(r"유효\s*등급", text, re.IGNORECASE):
            continue
        tokens = find_rating_tokens_in_text(text)
        if not tokens:
            continue

        words = page.get_text(
            "words",
            clip=pymupdf.Rect(clip.x0, line.y0 - 1, clip.x1, line.y1 + 1),
            sort=True,
        )
        left_parts: list[str] = []
        right_parts: list[str] = []
        for word in words:
            chunk = normalize_text(word[4])
            if not chunk:
                continue
            if find_rating_tokens_in_text(chunk):
                right_parts.append(chunk)
            elif right_parts:
                right_parts.append(chunk)
            else:
                left_parts.append(chunk)
        label = normalize_text(" ".join(left_parts))
        rating_part = normalize_text(" ".join(right_parts))
        if not rating_part:
            rating_part = tokens[0].rating_display
            if tokens[0].outlook:
                rating_part = f"{rating_part}/{tokens[0].outlook}"
        if not label:
            match = re.search(
                r"(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|"
                r"CCC?|CC|C|D|A[123])",
                text,
                re.IGNORECASE,
            )
            if match:
                label = normalize_text(text[: match.start()]).strip(" ·|-")
                rating_part = normalize_text(text[match.start() :])
        if label or rating_part:
            rows.append([label, rating_part])
    if not rows:
        return None
    return ExtractedTableGrid(
        section_key=SECTION_VALID,
        title_raw=title_raw,
        page=page.number + 1,
        headers=["구분", "등급"],
        rows=rows,
        region_id=region_id,
        source="visual_grid",
        bbox=(clip.x0, clip.y0, clip.x1, clip.y1),
    )


def _visual_financial_grid(
    page: pymupdf.Page,
    clip: pymupdf.Rect,
    *,
    title_raw: str,
    region_id: str,
    basis: str | None,
    unit_caption: str | None,
) -> ExtractedTableGrid | None:
    from extract.fin_tables import _visual_fin_grid

    fin = _visual_fin_grid(
        page,
        clip,
        page_number=page.number + 1,
        title_raw=title_raw,
        unit_caption=unit_caption,
        basis=basis,
    )
    if fin is None:
        return None
    return ExtractedTableGrid(
        section_key=SECTION_FINANCIAL,
        title_raw=fin.title_raw,
        page=fin.page,
        headers=fin.headers,
        rows=fin.rows,
        region_id=region_id,
        source=fin.source,
        basis=fin.basis,
        unit_caption=fin.unit_caption,
        footnotes=fin.footnotes,
        bbox=fin.bbox,
    )


def extract_table_grid(
    page: pymupdf.Page,
    clip: pymupdf.Rect,
    *,
    section_key: str,
    title_raw: str,
    region_id: str = "single",
    near_texts: list[str] | None = None,
) -> ExtractedTableGrid | None:
    """clip 안에서 섹션 유형에 맞는 그리드를 복원한다."""
    texts = near_texts or []
    basis = _detect_basis(texts) if section_key == SECTION_FINANCIAL else None
    unit_caption = (
        _detect_unit_caption(texts) if section_key == SECTION_FINANCIAL else None
    )

    grid = _extract_via_find_tables(
        page,
        clip,
        section_key=section_key,
        title_raw=title_raw,
        region_id=region_id,
        basis=basis,
        unit_caption=unit_caption,
    )
    if grid is not None:
        if section_key == SECTION_FINANCIAL:
            bottom = grid.bbox[3] if grid.bbox else clip.y1
            lines = extract_visual_lines(page)
            grid.footnotes = _extract_footnotes(lines, bottom)
        return grid

    if section_key == SECTION_PRIMARY:
        return _visual_primary_grid(
            page, clip, title_raw=title_raw, region_id=region_id
        )
    if section_key == SECTION_VALID:
        return _visual_valid_grid(
            page, clip, title_raw=title_raw, region_id=region_id
        )
    if section_key == SECTION_FINANCIAL:
        grid = _visual_financial_grid(
            page,
            clip,
            title_raw=title_raw,
            region_id=region_id,
            basis=basis,
            unit_caption=unit_caption,
        )
        if grid is not None:
            bottom = grid.bbox[3] if grid.bbox else clip.y1
            lines = extract_visual_lines(page)
            grid.footnotes = _extract_footnotes(lines, bottom)
        return grid
    return None
