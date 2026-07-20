"""표/시각 추출 실패 시 평문 줄 스캔 → ExtractedRatingRow."""

from __future__ import annotations

import pymupdf

from common.models import ExtractedRatingRow
from common.rating_tokens import find_rating_tokens_in_text
from common.text_utils import normalize_text
from extract.row_parser import (
    looks_like_instrument_label,
    looks_like_rating_row,
    parse_rating_row_values,
)


def extract_fallback_rows_from_text(
    page: pymupdf.Page,
) -> list[ExtractedRatingRow]:
    text = normalize_text(page.get_text("text", sort=True))
    lines = [
        normalize_text(line)
        for line in text.splitlines()
        if normalize_text(line)
    ]

    records: list[ExtractedRatingRow] = []
    row_index = 0

    for index, line in enumerate(lines):
        if not looks_like_rating_row(line):
            continue
        if not looks_like_instrument_label(line):
            continue

        row_parts = [line]

        if not find_rating_tokens_in_text(" ".join(row_parts)):
            for offset in range(1, 4):
                next_index = index + offset
                if next_index >= len(lines):
                    break

                next_line = lines[next_index]

                if looks_like_rating_row(next_line) and (
                    looks_like_instrument_label(next_line)
                ):
                    break

                row_parts.append(next_line)

                if find_rating_tokens_in_text(" ".join(row_parts)):
                    break

        record = parse_rating_row_values(
            values=row_parts,
            page_number=page.number + 1,
            row_index=row_index,
            section="fallback",
            source="plain_text",
        )
        if record:
            records.append(record)
            row_index += 1

    return records
