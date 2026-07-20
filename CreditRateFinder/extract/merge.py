"""추출 source 우선순위 병합 (primary 우선, valid는 보완만)."""

from __future__ import annotations

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


def _prefer_record(left: RatingRecord, right: RatingRecord) -> RatingRecord:
    """동일 상품 중복 시 single·높은 source 우선."""
    left_single = 0 if left.rating_status == "single" else 1
    right_single = 0 if right.rating_status == "single" else 1
    if left_single != right_single:
        return left if left_single < right_single else right

    left_rank = source_rank(left.source)
    right_rank = source_rank(right.source)
    if left_rank != right_rank:
        return left if left_rank < right_rank else right

    # primary section 선호
    left_primary = 0 if is_primary_record(left) else 1
    right_primary = 0 if is_primary_record(right) else 1
    if left_primary != right_primary:
        return left if left_primary < right_primary else right

    return left


def merge_rating_records(records: list[RatingRecord]) -> list[RatingRecord]:
    """primary에 있는 상품은 valid에서 제외하고, 동키는 source 우선으로 1건만 유지."""
    primary_keys: set[str] = set()
    for record in records:
        if is_primary_record(record):
            primary_keys.add(_record_merge_key(record))

    filtered: list[RatingRecord] = []
    for record in records:
        key = _record_merge_key(record)
        if (
            not is_primary_record(record)
            and record.source == "valid_rating_section"
            and key in primary_keys
        ):
            continue
        filtered.append(record)

    merged: dict[str, RatingRecord] = {}
    order: list[str] = []
    for record in filtered:
        key = _record_merge_key(record)
        existing = merged.get(key)
        if existing is None:
            merged[key] = record
            order.append(key)
        else:
            merged[key] = _prefer_record(existing, record)

    return [merged[key] for key in order]
