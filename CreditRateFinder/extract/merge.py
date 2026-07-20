"""Primary·유효등급 canonical 병합 및 교차검증."""

from __future__ import annotations

from dataclasses import replace

from common.models import ExtractedRatingRow, RatingRecord

SOURCE_PRIORITY: dict[str, int] = {
    "pdf_table": 0,
    "visual_layout": 1,
    "valid_rating_section": 2,
    "fallback": 3,
    "unknown": 9,
}

PRIMARY_SOURCES = frozenset({"pdf_table", "visual_layout"})


def source_rank(source: str | None) -> int:
    return SOURCE_PRIORITY.get(source or "unknown", 9)


def is_primary_record(record: RatingRecord | ExtractedRatingRow) -> bool:
    section = getattr(record, "section", None)
    source = getattr(record, "source", None)
    if section == "primary_rating":
        return True
    return source in PRIMARY_SOURCES


def _record_merge_key(record: RatingRecord) -> str:
    if record.instrument_key:
        return f"key:{record.instrument_key}"
    return f"label:{record.normalized_label}"


def _ratings_equal(left: RatingRecord, right: RatingRecord) -> bool:
    return (left.rating, left.outlook) == (right.rating, right.outlook)


def _prefer_canonical(left: RatingRecord, right: RatingRecord) -> RatingRecord:
    left_primary = 0 if is_primary_record(left) else 1
    right_primary = 0 if is_primary_record(right) else 1
    if left_primary != right_primary:
        return left if left_primary < right_primary else right

    left_rank = source_rank(left.source)
    right_rank = source_rank(right.source)
    if left_rank != right_rank:
        return left if left_rank < right_rank else right

    left_single = 0 if left.rating_status == "single" else 1
    right_single = 0 if right.rating_status == "single" else 1
    if left_single != right_single:
        return left if left_single < right_single else right

    return left


def _merge_pair(
    canonical: RatingRecord,
    other: RatingRecord,
    warnings: list[dict],
) -> RatingRecord:
    if _ratings_equal(canonical, other):
        confirmed = list(canonical.confirmed_by)
        if (
            other.source == "valid_rating_section"
            and "valid_rating_section" not in confirmed
        ):
            confirmed.append("valid_rating_section")
        return replace(canonical, confirmed_by=confirmed)

    if is_primary_record(canonical) and not is_primary_record(other):
        warnings.append(
            {
                "code": "conflicting_rating_sources",
                "instrument_key": canonical.instrument_key,
                "primary_rating": canonical.rating,
                "primary_outlook": canonical.outlook,
                "valid_rating": other.rating,
                "valid_outlook": other.outlook,
            }
        )
        return canonical

    if is_primary_record(other) and not is_primary_record(canonical):
        warnings.append(
            {
                "code": "conflicting_rating_sources",
                "instrument_key": other.instrument_key,
                "primary_rating": other.rating,
                "primary_outlook": other.outlook,
                "valid_rating": canonical.rating,
                "valid_outlook": canonical.outlook,
            }
        )
        return other

    return _prefer_canonical(canonical, other)


def merge_canonical_records(
    records: list[RatingRecord],
) -> tuple[list[RatingRecord], list[dict]]:
    """instrument_key별 canonical 병합 + confirmed_by·충돌 warning."""
    warnings: list[dict] = []
    grouped: dict[str, list[RatingRecord]] = {}
    order: list[str] = []

    for record in records:
        key = _record_merge_key(record)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(record)

    merged: list[RatingRecord] = []
    for key in order:
        group = grouped[key]
        canonical = group[0]
        for other in group[1:]:
            canonical = _merge_pair(canonical, other, warnings)
        merged.append(canonical)

    return merged, warnings


def merge_rating_records(records: list[RatingRecord]) -> list[RatingRecord]:
    """하위 호환: canonical 병합 결과만 반환."""
    merged, _warnings = merge_canonical_records(records)
    return merged
