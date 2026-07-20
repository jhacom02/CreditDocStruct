"""merged 평가 행 복원 — YAML longest-match 기반 분할."""

from __future__ import annotations

import re
from dataclasses import replace

from common.models import ExtractedRatingRow
from common.settings import InstrumentsConfig
from common.text_utils import normalize_label, normalize_text
from extract.label_fields import decompose_label_fields
from extract.row_parser import EVALUATION_TYPES

EVALUATION_ONLY_LABELS = frozenset(EVALUATION_TYPES)


def _active_labels(config: InstrumentsConfig) -> list[tuple[str, str]]:
    labels: list[tuple[str, str]] = []
    for entry in config.label_dictionary:
        if not entry.active:
            continue
        normalized = normalize_label(entry.raw_label)
        if normalized:
            labels.append((normalized, entry.instrument_key))
    labels.sort(key=lambda item: len(item[0]), reverse=True)
    return labels


def find_registered_label_spans(
    text: str,
    config: InstrumentsConfig,
) -> list[tuple[int, int, str, str]]:
    """(start, end, normalized_label, instrument_key) non-overlapping longest-first."""
    compact = normalize_label(text)
    if not compact:
        return []

    candidates: list[tuple[int, int, str, str]] = []
    for normalized, instrument_key in _active_labels(config):
        start = 0
        while True:
            index = compact.find(normalized, start)
            if index < 0:
                break
            candidates.append(
                (index, index + len(normalized), normalized, instrument_key)
            )
            start = index + 1

    candidates.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    spans: list[tuple[int, int, str, str]] = []
    used_ranges: list[tuple[int, int]] = []
    for start, end, normalized, instrument_key in candidates:
        if any(
            not (end <= used_start or start >= used_end)
            for used_start, used_end in used_ranges
        ):
            continue
        spans.append((start, end, normalized, instrument_key))
        used_ranges.append((start, end))

    spans.sort(key=lambda item: item[0])
    return spans


def is_merged_label_suspect(text: str, config: InstrumentsConfig) -> bool:
    spans = find_registered_label_spans(text, config)
    keys = {item[3] for item in spans}
    return len(keys) >= 2


def _split_text_by_spans(
    text: str,
    spans: list[tuple[int, int, str, str]],
) -> list[str]:
    if not spans:
        return [text]

    return [normalized for _s, _e, normalized, _key in spans]


def split_merged_row(
    row: ExtractedRatingRow,
    config: InstrumentsConfig,
) -> list[ExtractedRatingRow]:
    """merged 라벨을 상품별 ExtractedRatingRow로 분할한다."""
    label_source = row.label_text or row.raw_label or " ".join(row.cells)
    spans = find_registered_label_spans(label_source, config)
    if len({item[3] for item in spans}) < 2:
        return [row]

    labels = _split_text_by_spans(label_source, spans)
    rebuilt: list[ExtractedRatingRow] = []
    for offset, label in enumerate(labels):
        if label in EVALUATION_ONLY_LABELS:
            continue
        child = replace(
            row,
            raw_label=label,
            label_text=label,
            row_index=row.row_index + offset,
        )
        rebuilt.append(child)
    return rebuilt or [row]


def _is_bon_only_label(row: ExtractedRatingRow) -> bool:
    label = normalize_text(row.raw_label)
    return label in EVALUATION_ONLY_LABELS


def rebuild_merged_rows(
    rows: list[ExtractedRatingRow],
    config: InstrumentsConfig,
) -> tuple[list[ExtractedRatingRow], str | None]:
    """분류 전 merged 행을 복원한다. 복원 불가 시 오류 메시지를 반환."""
    rebuilt: list[ExtractedRatingRow] = []

    for row in rows:
        decomposed = decompose_label_fields(row, config=config)

        if _is_bon_only_label(decomposed):
            return [], "evaluation_type_only_label"

        label_text = decomposed.label_text or decomposed.raw_label
        if is_merged_label_suspect(label_text, config):
            split_rows = split_merged_row(decomposed, config)
            if len(split_rows) <= 1:
                return [], "merged_row_rebuild_failed"
            rebuilt.extend(split_rows)
            continue

        if is_merged_label_suspect(decomposed.raw_label, config):
            split_rows = split_merged_row(decomposed, config)
            if len(split_rows) <= 1:
                return [], "merged_row_rebuild_failed"
            rebuilt.extend(split_rows)
            continue

        rebuilt.append(decomposed)

    return rebuilt, None
