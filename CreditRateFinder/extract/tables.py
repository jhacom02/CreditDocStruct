"""PDF 표 → ExtractedRatingRow (헤더 열 인덱스·bbox 행 그룹핑 유지)."""

from __future__ import annotations

import re
from statistics import median

import pymupdf

from agency.agency import get_agency_layout, is_rating_table_header
from common.models import ExtractedRatingRow
from common.rating_tokens import find_rating_tokens_in_text
from common.text_utils import normalize_text
from extract.row_parser import looks_like_rating_row, parse_rating_row_values


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


def _row_y_center(cells: list[pymupdf.Rect | None]) -> float | None:
    rects = [cell for cell in cells if cell is not None]
    if not rects:
        return None
    return median((rect.y0 + rect.y1) / 2 for rect in rects)


def _group_matrix_by_bbox_rows(
    table: object,
    cleaned_matrix: list[list[str]],
    header_index: int,
    col_count: int,
    *,
    y_tolerance: float = 6.0,
) -> list[list[str]] | None:
    cells_attr = getattr(table, "cells", None)
    if not cells_attr:
        return None

    try:
        row_count = len(cleaned_matrix)
        grouped: list[list[str]] = []
        current_row_index: int | None = None
        current_values: list[str] | None = None

        for row_index in range(header_index + 1, row_count):
            row_cells: list[pymupdf.Rect | None] = []
            row_values = cleaned_matrix[row_index]
            aligned = list(row_values[:col_count])
            while len(aligned) < col_count:
                aligned.append("")

            for col_index in range(col_count):
                try:
                    rect = cells_attr[row_index][col_index]
                except (IndexError, TypeError):
                    rect = None
                row_cells.append(rect)

            y_center = _row_y_center(row_cells)
            if y_center is None:
                if any(aligned):
                    grouped.append(aligned)
                continue

            if current_row_index is None:
                current_row_index = row_index
                current_values = aligned
                continue

            prev_cells = [
                cells_attr[current_row_index][col_index]
                if col_index < len(cells_attr[current_row_index])
                else None
                for col_index in range(col_count)
            ]
            prev_y = _row_y_center(prev_cells)
            same_band = (
                prev_y is not None and abs(y_center - prev_y) <= y_tolerance
            )

            if same_band and current_values is not None:
                for index, value in enumerate(aligned):
                    if value and not current_values[index]:
                        current_values[index] = value
                    elif value and current_values[index]:
                        current_values[index] = (
                            f"{current_values[index]} {value}"
                        ).strip()
            else:
                if current_values is not None and any(current_values):
                    grouped.append(current_values)
                current_row_index = row_index
                current_values = aligned

        if current_values is not None and any(current_values):
            grouped.append(current_values)

        return grouped if grouped else None
    except Exception:
        return None


def _group_rows_heuristic(
    cleaned_matrix: list[list[str]],
    header_index: int,
    col_count: int,
) -> list[list[str]]:
    grouped_rows: list[list[str]] = []
    current_group: list[str] | None = None

    for row in cleaned_matrix[header_index + 1 :]:
        aligned = list(row[:col_count])
        while len(aligned) < col_count:
            aligned.append("")

        nonempty = [value for value in aligned if value]
        if not nonempty:
            continue

        row_text = normalize_text(" ".join(nonempty))
        starts_new = looks_like_rating_row(row_text)

        if not starts_new and current_group is not None:
            if find_rating_tokens_in_text(" ".join(nonempty)):
                for index, value in enumerate(aligned):
                    if value and not current_group[index]:
                        current_group[index] = value
                    elif value and current_group[index]:
                        current_group[index] = (
                            f"{current_group[index]} {value}"
                        ).strip()
                continue

        if starts_new:
            if current_group is not None:
                grouped_rows.append(current_group)
            current_group = list(aligned)
        elif current_group is not None:
            for index, value in enumerate(aligned):
                if value and not current_group[index]:
                    current_group[index] = value
                elif value and current_group[index]:
                    current_group[index] = (
                        f"{current_group[index]} {value}"
                    ).strip()

    if current_group is not None:
        grouped_rows.append(current_group)

    return grouped_rows


def extract_primary_rows_from_tables(
    page: pymupdf.Page,
    agency: str,
) -> list[ExtractedRatingRow]:
    records: list[ExtractedRatingRow] = []
    layout = get_agency_layout(agency)
    row_index = 0

    try:
        finder = page.find_tables()
        tables = finder.tables
    except Exception:
        return records

    for table in tables:
        try:
            matrix = table.extract()
        except Exception:
            continue

        if not matrix:
            continue

        cleaned_matrix = [
            [normalize_text(cell) for cell in row] for row in matrix
        ]

        header_index: int | None = None
        for index, row in enumerate(cleaned_matrix):
            row_text = _compact(" ".join(cell for cell in row if cell))
            if is_rating_table_header(row_text, layout):
                header_index = index
                break

        if header_index is None:
            continue

        header_cells = list(cleaned_matrix[header_index])
        col_count = len(header_cells)

        grouped_rows = _group_matrix_by_bbox_rows(
            table,
            cleaned_matrix,
            header_index,
            col_count,
        )
        if grouped_rows is None:
            grouped_rows = _group_rows_heuristic(
                cleaned_matrix, header_index, col_count
            )

        for row_values in grouped_rows:
            record = parse_rating_row_values(
                values=row_values,
                page_number=page.number + 1,
                row_index=row_index,
                section="primary_rating",
                source="pdf_table",
                header_cells=header_cells,
            )
            if record:
                records.append(record)
                row_index += 1

    return records
