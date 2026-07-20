"""PDF 표 → ExtractedRatingRow (헤더 열 인덱스 유지)."""

from __future__ import annotations

import re

import pymupdf

from agency.agency import get_agency_layout, is_rating_table_header
from common.models import ExtractedRatingRow
from common.rating_tokens import find_rating_tokens_in_text
from common.text_utils import normalize_text
from extract.row_parser import looks_like_rating_row, parse_rating_row_values


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


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

        # 열 정렬을 유지한 채 행을 그룹핑 (빈 셀도 자리 유지)
        grouped_rows: list[list[str]] = []
        current_group: list[str] | None = None

        for row in cleaned_matrix[header_index + 1 :]:
            # 헤더 길이에 맞춤
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
                    # 이어지는 등급 조각: 빈 칸에만 채움
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
