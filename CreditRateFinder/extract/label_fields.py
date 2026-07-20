"""평가대상 라벨 분해 — YAML prefix 기준 raw_label / issue_name 분리."""

from __future__ import annotations

import re

from common.models import ExtractedRatingRow
from common.settings import InstrumentsConfig
from common.text_utils import normalize_label, normalize_text
from extract.row_parser import (
    EVALUATION_TYPES,
    find_header_column_index,
    infer_target_label,
)

ISSUE_HEADER_NAMES = ("종목", "회차", "종목명")
REMARK_HINTS = (
    "상각형",
    "비상각형",
    "원화",
    "외화",
    "달러",
    "유로",
    "고정",
    "변동",
)


def find_prefix_label_match(
    text: str,
    config: InstrumentsConfig,
) -> tuple[str, str, str] | None:
    """행 앞부분 YAML 최장 alias → (raw_label, issue_remainder, instrument_key)."""
    normalized_full = normalize_label(text)
    if not normalized_full:
        return None

    best_raw: str | None = None
    best_norm: str | None = None
    best_key: str | None = None

    for entry in config.label_dictionary:
        if not entry.active:
            continue
        alias_norm = normalize_label(entry.raw_label)
        if not alias_norm:
            continue
        if not normalized_full.startswith(alias_norm):
            continue
        if best_norm is None or len(alias_norm) > len(best_norm):
            best_raw = entry.raw_label
            best_norm = alias_norm
            best_key = entry.instrument_key

    if best_raw is None or best_norm is None or best_key is None:
        return None

    original = normalize_text(text)
    split_at = len(original)
    for end in range(1, len(original) + 1):
        if normalize_label(original[:end]) == best_norm:
            split_at = end
            break

    issue_remainder = normalize_text(original[split_at:])
    return best_raw, issue_remainder, best_key


def split_label_and_issue(
    text: str,
    config: InstrumentsConfig,
) -> tuple[str, str | None]:
    """행 앞부분 YAML 최장 alias → raw_label, 나머지 원문 → issue_name."""
    matched = find_prefix_label_match(text, config)
    if matched is None:
        return normalize_text(text), None
    raw_label, issue_name, _instrument_key = matched
    return raw_label, issue_name or None


def _strip_evaluation_suffix(text: str) -> tuple[str, str | None]:
    """라벨 끝의 평가 종류를 분리한다."""
    normalized = normalize_text(text)
    if not normalized:
        return "", None

    evaluation_type: str | None = None
    for eval_type in sorted(EVALUATION_TYPES, key=len, reverse=True):
        if normalized == eval_type:
            return "", eval_type
        if normalized.endswith(f" {eval_type}"):
            normalized = normalized[: -len(eval_type)].strip()
            evaluation_type = eval_type
            break

    return normalized, evaluation_type


def _extract_remark(text: str) -> tuple[str, str | None]:
    normalized = normalize_text(text)
    for hint in REMARK_HINTS:
        if hint in normalized:
            return normalize_text(normalized.replace(hint, "").strip()), hint
    return normalized, None


def _issue_from_separate_column(
    cells: list[str],
    header: list[str] | None,
    raw_label: str,
) -> str | None:
    """종목/회차 열이 라벨 셀과 다를 때만 issue_name으로 사용."""
    if not header:
        return None
    label_index = find_header_column_index(
        header, ("평가대상", "구분", "종목")
    )
    issue_index = find_header_column_index(header, ISSUE_HEADER_NAMES)
    if issue_index is None or issue_index >= len(cells):
        return None
    if label_index is not None and issue_index == label_index:
        return None
    value = normalize_text(cells[issue_index])
    if not value or value == raw_label:
        return None
    if value in EVALUATION_TYPES:
        return None
    return value


def decompose_label_fields(
    row: ExtractedRatingRow,
    *,
    header_cells: list[str] | None = None,
    config: InstrumentsConfig | None = None,
) -> ExtractedRatingRow:
    """raw_label·issue_name·remark·label_text·evaluation_type을 정제한다."""
    cells = row.cells or []
    header = header_cells

    label_text = normalize_text(
        " ".join(value for value in cells if value) or row.raw_label
    )
    base_label = infer_target_label(cells, header) or row.raw_label

    raw_label = base_label
    issue_name: str | None = None
    remark: str | None = row.remark
    yaml_split = False

    if config is not None:
        matched = find_prefix_label_match(base_label, config)
        if matched is not None:
            raw_label, issue_name, _instrument_key = matched
            issue_name = issue_name or None
            yaml_split = True

    column_issue = _issue_from_separate_column(cells, header, raw_label)
    if column_issue:
        issue_name = column_issue

    stripped, eval_from_label = _strip_evaluation_suffix(raw_label)
    if not yaml_split:
        raw_label, remark = _extract_remark(stripped)

    evaluation_type = row.evaluation_type or eval_from_label

    remark_cell_index = find_header_column_index(header, ("비고",))
    if remark_cell_index is not None and remark_cell_index < len(cells):
        remark_value = normalize_text(cells[remark_cell_index])
        if remark_value:
            remark = remark_value

    return ExtractedRatingRow(
        raw_label=raw_label or base_label,
        rating_cells=row.rating_cells,
        rating_status=row.rating_status,
        rating=row.rating,
        outlook=row.outlook,
        raw_outlook=row.raw_outlook,
        page=row.page,
        row_index=row.row_index,
        section=row.section,
        source=row.source,
        cells=cells,
        evaluation_type=evaluation_type,
        issue_name=issue_name,
        remark=remark,
        label_text=label_text or row.raw_label,
    )


def apply_label_fields_to_rows(
    rows: list[ExtractedRatingRow],
    *,
    header_cells: list[str] | None = None,
    config: InstrumentsConfig | None = None,
) -> list[ExtractedRatingRow]:
    return [
        decompose_label_fields(
            row, header_cells=header_cells, config=config
        )
        for row in rows
    ]
