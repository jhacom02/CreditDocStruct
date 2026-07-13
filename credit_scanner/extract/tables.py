from __future__ import annotations

import pymupdf

from credit_scanner.agency import get_agency_layout, is_rating_table_header
from credit_scanner.classifier import InstrumentClassifier, get_classifier
from credit_scanner.extract.row_parser import (
    looks_like_rating_row,
    parse_rating_row_values,
)
from credit_scanner.models import RatingRecord
from credit_scanner.rating_tokens import find_rating_tokens, tokenize_values
from credit_scanner.text_utils import compact_text, normalize_text


def extract_primary_rows_from_tables(
    page: pymupdf.Page,
    agency: str,
    file_name: str,
    classifier: InstrumentClassifier | None = None,
) -> list[RatingRecord]:
    records: list[RatingRecord] = []
    layout = get_agency_layout(agency)
    active = classifier or get_classifier()

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
            row_text = compact_text(" ".join(row))
            if is_rating_table_header(row_text, layout):
                header_index = index
                break

        if header_index is None:
            continue

        grouped_rows: list[list[str]] = []
        current_group: list[str] = []

        for row in cleaned_matrix[header_index + 1:]:
            row_values = [value for value in row if value]

            if not row_values:
                continue

            row_text = normalize_text(" ".join(row_values))
            starts_new = looks_like_rating_row(row_text, active)

            if not starts_new and current_group:
                if find_rating_tokens(tokenize_values(row_values)):
                    current_group.extend(row_values)
                    continue

            if starts_new:
                if current_group:
                    grouped_rows.append(current_group)
                current_group = row_values
            elif current_group:
                current_group.extend(row_values)

        if current_group:
            grouped_rows.append(current_group)

        for row_values in grouped_rows:
            record = parse_rating_row_values(
                values=row_values,
                agency=agency,
                file_name=file_name,
                page_number=page.number + 1,
                section="primary_rating",
                source="pdf_table",
                confidence=0.99,
                classifier=active,
            )
            if record:
                records.append(record)

    return records
