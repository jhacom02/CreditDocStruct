from __future__ import annotations

import pymupdf

from credit_scanner.classifier import InstrumentClassifier, get_classifier
from credit_scanner.extract.row_parser import (
    looks_like_rating_row,
    parse_rating_row_values,
)
from credit_scanner.models import RatingRecord
from credit_scanner.rating_tokens import find_rating_tokens, tokenize_values
from credit_scanner.text_utils import normalize_text


def extract_fallback_rows_from_text(
    page: pymupdf.Page,
    agency: str,
    file_name: str,
    classifier: InstrumentClassifier | None = None,
) -> list[RatingRecord]:
    active = classifier or get_classifier()
    text = normalize_text(page.get_text("text", sort=True))
    lines = [
        normalize_text(line)
        for line in text.splitlines()
        if normalize_text(line)
    ]

    records: list[RatingRecord] = []

    for index, line in enumerate(lines):
        if not looks_like_rating_row(line, active):
            continue
        if not active.looks_like_instrument_row(line):
            continue

        row_parts = [line]

        if not find_rating_tokens(tokenize_values(row_parts)):
            for offset in range(1, 4):
                next_index = index + offset
                if next_index >= len(lines):
                    break

                next_line = lines[next_index]

                if looks_like_rating_row(next_line, active) and (
                    active.looks_like_instrument_row(next_line)
                ):
                    break

                row_parts.append(next_line)

                if find_rating_tokens(tokenize_values(row_parts)):
                    break

        record = parse_rating_row_values(
            values=row_parts,
            agency=agency,
            file_name=file_name,
            page_number=page.number + 1,
            section="fallback",
            source="plain_text",
            confidence=0.65,
            classifier=active,
        )
        if record:
            records.append(record)

    return records
