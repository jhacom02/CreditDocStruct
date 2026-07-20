"""셀/줄 → ExtractedRatingRow 조립 (행 전체 등급 탐색·현재등급 열 선택)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from common.models import ExtractedRatingRow, RatingStatus
from common.rating_tokens import (
    OUTLOOK_TOKEN_RE,
    RatingToken,
    count_rating_tokens_in_cell,
    find_rating_tokens_in_text,
    normalize_outlook,
)
from common.text_utils import normalize_text

HEADER_NOISE_TOKENS = (
    "평가대상",
    "구분",
    "종류",
    "현재등급",
    "직전등급",
    "ratingaction",
    "비고",
    "종목",
)

EVALUATION_TYPES = {
    "본",
    "본평가",
    "신규",
    "신규평가",
    "예비",
    "예비평가",
    "수시",
    "수시평가",
    "정기",
    "정기평가",
}

PRIMARY_EVAL_TYPES = frozenset({"본", "본평가"})

RATING_ACTIONS = {
    "유지",
    "상향",
    "하향",
    "신규",
    "취소",
    "부여",
    "상향검토",
    "하향검토",
    "Watchlist",
}

CURRENT_RATING_HEADER_NAMES = ("현재등급", "현재 등급", "currentrating")
PREVIOUS_RATING_HEADER_NAMES = ("직전등급", "직전 등급", "previousrating")
EVAL_TYPE_HEADER_NAMES = ("종류", "평가종류", "구분")
TARGET_LABEL_HEADER_NAMES = ("평가대상", "구분", "종목")


@dataclass(frozen=True)
class _RatingCandidate:
    cell_index: int
    token: RatingToken


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


def looks_like_rating_row(text: str | None) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False

    compact = _compact(normalized)
    if any(noise in compact for noise in HEADER_NOISE_TOKENS):
        if not find_rating_tokens_in_text(normalized):
            return False

    if find_rating_tokens_in_text(normalized) and len(normalized) >= 4:
        return True

    hints = (
        "등급",
        "사채",
        "채권",
        "증권",
        "어음",
        "발행자",
        "issuer",
        "rating",
        "coco",
        "abs",
        "cp",
        "보험",
    )
    return any(hint in compact for hint in hints)


def looks_like_instrument_label(text: str | None) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    compact = _compact(normalized)
    hints = (
        "등급",
        "사채",
        "채권",
        "증권",
        "어음",
        "발행자",
        "issuer",
        "rating",
        "coco",
        "abs",
        "cp",
        "보험",
        "자본",
    )
    return any(hint in compact for hint in hints)


def _is_noise_label(value: str) -> bool:
    from common.rating_tokens import parse_rating_value

    compact = _compact(value)
    if not compact:
        return True
    if any(noise in compact for noise in HEADER_NOISE_TOKENS):
        return True
    if value in EVALUATION_TYPES or value in RATING_ACTIONS:
        return True
    if parse_rating_value(value):
        return True
    if OUTLOOK_TOKEN_RE.fullmatch(value):
        return True
    return False


def infer_raw_label(cleaned_values: list[str]) -> str:
    for value in cleaned_values:
        if _is_noise_label(value):
            continue
        return value
    return cleaned_values[0] if cleaned_values else ""


def infer_target_label(
    cells: list[str],
    header_cells: list[str] | None,
) -> str:
    index = find_header_column_index(
        header_cells, TARGET_LABEL_HEADER_NAMES
    )
    if index is not None and index < len(cells):
        value = normalize_text(cells[index])
        if value and value not in EVALUATION_TYPES:
            return value

    return infer_raw_label([value for value in cells if value])


def find_header_column_index(
    header_cells: list[str] | None,
    names: tuple[str, ...] = CURRENT_RATING_HEADER_NAMES,
) -> int | None:
    if not header_cells:
        return None

    targets = {_compact(name) for name in names if name}
    for index, cell in enumerate(header_cells):
        compact = _compact(cell)
        if not compact:
            continue
        if any(target in compact for target in targets):
            return index
    return None


def infer_evaluation_type(
    cells: list[str],
    header_cells: list[str] | None = None,
) -> str | None:
    type_index = find_header_column_index(header_cells, EVAL_TYPE_HEADER_NAMES)
    if type_index is not None and type_index < len(cells):
        value = normalize_text(cells[type_index])
        if value in EVALUATION_TYPES:
            return value

    for cell in cells:
        value = normalize_text(cell)
        if value in EVALUATION_TYPES:
            return value
    return None


def _collect_rating_cells(cleaned_values: list[str]) -> list[str]:
    rating_cells: list[str] = []
    for cell in cleaned_values:
        if count_rating_tokens_in_cell(cell) > 0:
            if OUTLOOK_TOKEN_RE.fullmatch(cell) and not find_rating_tokens_in_text(
                cell
            ):
                continue
            rating_cells.append(cell)
    return rating_cells


def _collect_row_rating_candidates(cells: list[str]) -> list[_RatingCandidate]:
    candidates: list[_RatingCandidate] = []
    for index, cell in enumerate(cells):
        value = normalize_text(cell)
        if not value:
            continue
        for token in find_rating_tokens_in_text(value):
            candidates.append(_RatingCandidate(cell_index=index, token=token))
    return candidates


def _token_from_candidate(
    candidate: _RatingCandidate,
    cells: list[str],
) -> tuple[str, str | None, str | None]:
    rating = candidate.token.rating
    outlook = candidate.token.outlook
    raw_outlook = candidate.token.raw_outlook

    if outlook is None and candidate.cell_index < len(cells) - 1:
        next_cell = cells[candidate.cell_index + 1]
        outlook_match = OUTLOOK_TOKEN_RE.fullmatch(next_cell)
        if outlook_match:
            raw_outlook = next_cell
            outlook = normalize_outlook(outlook_match.group("outlook"))

    return rating, outlook, raw_outlook


def _resolve_row_rating(
    cells: list[str],
    header_cells: list[str] | None,
) -> tuple[str | None, str | None, str | None, RatingStatus, list[str]]:
    candidates = _collect_row_rating_candidates(cells)
    rating_cells = _collect_rating_cells(cells)

    if not candidates:
        return None, None, None, "none", rating_cells

    if len(candidates) == 1:
        rating, outlook, raw_outlook = _token_from_candidate(
            candidates[0], cells
        )
        return rating, outlook, raw_outlook, "single", rating_cells

    current_index = find_header_column_index(
        header_cells, CURRENT_RATING_HEADER_NAMES
    )
    if current_index is None:
        return None, None, None, "ambiguous", rating_cells

    current_candidates = [
        item for item in candidates if item.cell_index == current_index
    ]
    if len(current_candidates) == 1:
        rating, outlook, raw_outlook = _token_from_candidate(
            current_candidates[0], cells
        )
        return rating, outlook, raw_outlook, "single", rating_cells

    return None, None, None, "ambiguous", rating_cells


def parse_rating_row_values(
    values: list[str],
    *,
    page_number: int,
    row_index: int,
    section: str,
    source: str,
    header_cells: list[str] | None = None,
    current_rating_cell: str | None = None,
) -> ExtractedRatingRow | None:
    if header_cells is not None and len(values) == len(header_cells):
        cells = [normalize_text(value) for value in values]
        cleaned_values = [value for value in cells if value]
    else:
        cleaned_values = [
            normalize_text(value) for value in values if normalize_text(value)
        ]
        cells = cleaned_values

    if current_rating_cell and normalize_text(current_rating_cell):
        index = find_header_column_index(
            header_cells, CURRENT_RATING_HEADER_NAMES
        )
        if index is not None and index < len(cells):
            cells = list(cells)
            cells[index] = normalize_text(current_rating_cell)

    if not cleaned_values and not any(cells):
        return None

    scan_values = cells if any(cells) else cleaned_values

    rating, outlook, raw_outlook, rating_status, rating_cells = (
        _resolve_row_rating(scan_values, header_cells)
    )

    evaluation_type = infer_evaluation_type(scan_values, header_cells)
    if header_cells is not None and len(values) == len(header_cells):
        raw_label = infer_target_label(cells, header_cells)
    else:
        raw_label = infer_raw_label(
            cleaned_values if cleaned_values else scan_values
        )

    if rating_status == "none" and not raw_label:
        return None
    if rating_status == "none" and not looks_like_instrument_label(raw_label):
        if not looks_like_rating_row(" ".join(cleaned_values or scan_values)):
            return None

    return ExtractedRatingRow(
        raw_label=raw_label,
        rating_cells=rating_cells,
        rating_status=rating_status,
        rating=rating,
        outlook=outlook,
        raw_outlook=raw_outlook,
        page=page_number,
        row_index=row_index,
        section=section,
        source=source,
        cells=scan_values,
        evaluation_type=evaluation_type,
        label_text=normalize_text(" ".join(scan_values)),
    )
