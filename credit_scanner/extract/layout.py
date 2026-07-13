from __future__ import annotations

import re

import pymupdf

from credit_scanner.agency import get_agency_layout
from credit_scanner.classifier import InstrumentClassifier, get_classifier
from credit_scanner.extract.row_parser import (
    classify_instrument,
    looks_like_rating_row,
    parse_rating_row_values,
)
from credit_scanner.extract.visual import extract_visual_lines, find_heading_line
from credit_scanner.models import RatingRecord
from credit_scanner.rating_tokens import find_rating_tokens, tokenize_values
from credit_scanner.text_utils import normalize_evaluation_type, normalize_text


def extract_primary_rows_from_visual_layout(
    page: pymupdf.Page,
    agency: str,
    file_name: str,
    classifier: InstrumentClassifier | None = None,
) -> list[RatingRecord]:
    layout = get_agency_layout(agency)
    active = classifier or get_classifier()
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
    records: list[RatingRecord] = []

    for index, line in enumerate(section_lines):
        if not looks_like_rating_row(line.text, active):
            continue

        if (
            find_rating_tokens(tokenize_values([line.text]))
            and not active.looks_like_instrument_row(line.text)
            and len(normalize_text(line.text)) < 12
        ):
            continue

        row_parts = [line.text]

        for offset in range(1, 4):
            next_index = index + offset
            if next_index >= len(section_lines):
                break

            next_line = section_lines[next_index]

            if looks_like_rating_row(next_line.text, active) and (
                active.looks_like_instrument_row(next_line.text)
                or classify_instrument(next_line.text, classifier=active)
            ):
                break

            if next_line.y0 - line.y1 > 45:
                break

            row_parts.append(next_line.text)
            combined_tokens = tokenize_values(row_parts)

            if find_rating_tokens(combined_tokens):
                if any(
                    normalize_evaluation_type(token)
                    for token in combined_tokens
                ):
                    break

        record = parse_rating_row_values(
            values=row_parts,
            agency=agency,
            file_name=file_name,
            page_number=page.number + 1,
            section="primary_rating",
            source="visual_layout",
            confidence=0.92,
            classifier=active,
        )
        if record:
            records.append(record)

    return records


def extract_valid_rating_rows(
    page: pymupdf.Page,
    agency: str,
    file_name: str,
    classifier: InstrumentClassifier | None = None,
) -> list[RatingRecord]:
    layout = get_agency_layout(agency)
    active = classifier or get_classifier()
    all_lines = extract_visual_lines(page)

    heading = find_heading_line(all_lines, layout.valid_rating_patterns)
    if not heading:
        return []

    left_x = max(0, heading.x0 - 10)
    right_x = min(
        page.rect.width,
        heading.x0
        + min(
            layout.valid_rating_max_width,
            page.rect.width * layout.valid_rating_width_ratio,
        ),
    )
    end_y = page.rect.height

    for line in all_lines:
        if line.y0 <= heading.y1 + 5:
            continue
        if line.x0 > right_x:
            continue
        if any(
            re.search(pattern, normalize_text(line.text), re.IGNORECASE)
            for pattern in layout.valid_rating_end_patterns
        ):
            end_y = min(end_y, line.y0)

    clip = pymupdf.Rect(left_x, heading.y1, right_x, end_y)
    section_lines = extract_visual_lines(page, clip=clip)
    records: list[RatingRecord] = []

    for index, line in enumerate(section_lines):
        if not looks_like_rating_row(line.text, active):
            continue

        row_parts = [line.text]
        parsed_tokens = find_rating_tokens(tokenize_values(row_parts))

        if not parsed_tokens and index + 1 < len(section_lines):
            next_line = section_lines[index + 1]
            if (
                not looks_like_rating_row(next_line.text, active)
                or not active.looks_like_instrument_row(next_line.text)
            ) and next_line.y0 - line.y1 <= 30:
                if not active.looks_like_instrument_row(next_line.text):
                    row_parts.append(next_line.text)

        record = parse_rating_row_values(
            values=row_parts,
            agency=agency,
            file_name=file_name,
            page_number=page.number + 1,
            section="valid_ratings",
            source="valid_rating_section",
            confidence=0.90,
            classifier=active,
        )
        if not record:
            continue

        record.evaluation_type = None
        record.previous_rating = None
        record.previous_outlook = None
        record.previous_rating_display = None
        record.rating_action = None
        records.append(record)

    return records
