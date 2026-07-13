from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pymupdf

from credit_scanner.agency import detect_agency
from credit_scanner.classifier import get_classifier
from credit_scanner.constants import EVALUATION_TYPES
from credit_scanner.extract import (
    extract_fallback_rows_from_text,
    extract_primary_rows_from_tables,
    extract_primary_rows_from_visual_layout,
    extract_valid_rating_rows,
)
from credit_scanner.models import RatingRecord
from credit_scanner.text_utils import compact_text


def deduplicate_records(records: list[RatingRecord]) -> list[RatingRecord]:
    unique: dict[
        tuple[
            str,
            str,
            str | None,
            str,
            str | None,
            str | None,
            str | None,
            str,
        ],
        RatingRecord,
    ] = {}

    for record in records:
        key = (
            record.section,
            record.instrument_type,
            record.evaluation_type,
            record.current_rating,
            record.current_outlook,
            record.previous_rating,
            record.issue_name,
            compact_text(record.raw_label),
        )
        existing = unique.get(key)
        if existing is None or record.confidence > existing.confidence:
            unique[key] = record

    return list(unique.values())


def record_priority(record: RatingRecord) -> tuple[int, int, float]:
    section_priority = {
        "primary_rating": 300,
        "valid_ratings": 200,
        "fallback": 100,
    }.get(record.section, 0)

    evaluation_priority = EVALUATION_TYPES.get(
        record.evaluation_type or "",
        0,
    )

    return (section_priority, evaluation_priority, record.confidence)


def select_target_rating(
    records: list[RatingRecord],
    target_instrument: str = "coco_t1",
) -> RatingRecord | None:
    matched = [
        record
        for record in records
        if record.classification_status == "matched"
    ]

    if target_instrument in {"coco", "coco_any"}:
        t1_candidates = [
            r for r in matched if r.instrument_type == "coco_t1"
        ]
        if t1_candidates:
            return max(t1_candidates, key=record_priority)

        t2_candidates = [
            r for r in matched if r.instrument_type == "coco_t2"
        ]
        if t2_candidates:
            return max(t2_candidates, key=record_priority)

        return None

    candidates = [
        r for r in matched if r.instrument_type == target_instrument
    ]
    if not candidates:
        return None

    return max(candidates, key=record_priority)


def select_best_by_instrument(
    records: list[RatingRecord],
) -> dict[str, RatingRecord]:
    result: dict[str, RatingRecord] = {}

    for record in records:
        if record.classification_status != "matched":
            continue

        existing = result.get(record.instrument_type)
        if (
            existing is None
            or record_priority(record) > record_priority(existing)
        ):
            result[record.instrument_type] = record

    return result


def collect_review_records(
    records: list[RatingRecord],
) -> list[RatingRecord]:
    return [
        record
        for record in records
        if record.classification_status in {"unknown", "ambiguous"}
    ]


def extract_credit_report(
    pdf_path: str | Path,
    target_instrument: str = "coco_t1",
    max_pages: int = 3,
    taxonomy_path: str | Path | None = None,
) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    classifier = get_classifier(
        str(taxonomy_path) if taxonomy_path else None
    )

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF 파일을 찾을 수 없습니다: {pdf_path}"
        )

    records: list[RatingRecord] = []

    with pymupdf.open(pdf_path) as document:
        pages_to_check = min(max_pages, len(document))
        extracted_text_length = 0

        for page_index in range(pages_to_check):
            page_text = document[page_index].get_text("text")
            extracted_text_length += len(page_text.strip())

        if extracted_text_length < 50:
            return {
                "file_name": pdf_path.name,
                "file_path": str(pdf_path),
                "agency": "미확인",
                "status": "ocr_required",
                "target_instrument": target_instrument,
                "selected": None,
                "ratings": {},
                "records": [],
                "review_records": [],
            }

        first_page = document[0]
        first_page_text = first_page.get_text("text", sort=True)
        agency = detect_agency(first_page_text)

        records.extend(
            extract_primary_rows_from_tables(
                page=first_page,
                agency=agency,
                file_name=pdf_path.name,
                classifier=classifier,
            )
        )
        records.extend(
            extract_primary_rows_from_visual_layout(
                page=first_page,
                agency=agency,
                file_name=pdf_path.name,
                classifier=classifier,
            )
        )
        records.extend(
            extract_valid_rating_rows(
                page=first_page,
                agency=agency,
                file_name=pdf_path.name,
                classifier=classifier,
            )
        )

        if not records:
            records.extend(
                extract_fallback_rows_from_text(
                    page=first_page,
                    agency=agency,
                    file_name=pdf_path.name,
                    classifier=classifier,
                )
            )

    records = deduplicate_records(records)
    review_records = collect_review_records(records)
    selected = select_target_rating(
        records=records,
        target_instrument=target_instrument,
    )
    best_by_instrument = select_best_by_instrument(records)

    if selected:
        status = "success"
    elif review_records and target_instrument in {
        "coco",
        "coco_any",
        "coco_t1",
        "coco_t2",
        "issuer",
        "senior_unsecured",
    }:
        status = "needs_review"
    elif target_instrument in {
        "coco",
        "coco_any",
        "coco_t1",
        "coco_t2",
    }:
        status = "needs_review"
    else:
        status = "not_found"

    return {
        "file_name": pdf_path.name,
        "file_path": str(pdf_path),
        "agency": records[0].agency if records else detect_agency(""),
        "status": status,
        "target_instrument": target_instrument,
        "selected": asdict(selected) if selected else None,
        "ratings": {
            instrument_type: asdict(record)
            for instrument_type, record in best_by_instrument.items()
        },
        "records": [asdict(record) for record in records],
        "review_records": [asdict(record) for record in review_records],
    }
