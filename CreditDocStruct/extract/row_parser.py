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
    parse_rating_value,
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

_VALID_NOISE_PATTERNS = (
    r"BIS\s*자본",
    r"BIS자본",
    r"BIS기준",
    r"ROA\s*\(",
    r"ROA\(",
    r"ROE\s*\(",
    r"NIM\s*\(",
    r"총자산",
    r"등급\s*추이",
    r"자기자본",
    r"부채비율",
    r"유동성비율",
    r"이중\s*레버리지",
    r"레버리지",
    r"Peer",
    r"PEER",
    r"충당금",
    r"고정이하",
    r"요주의",
    r"적용재무제표",
)


def truncate_valid_row_text(text: str) -> str:
    """유효등급 행에서 재무지표·등급추이 등 노이즈 이전까지만 유지."""
    normalized = normalize_text(text)
    if not normalized:
        return ""

    cut_index = len(normalized)
    for pattern in _VALID_NOISE_PATTERNS:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            cut_index = min(cut_index, match.start())

    trimmed = normalize_text(normalized[:cut_index])
    if not trimmed:
        return normalized

    if find_rating_tokens_in_text(trimmed):
        return trimmed

    return normalized


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

    # visual_layout은 표 한 행 전체가 단일 cell로 들어올 수 있다.
    combined = normalize_text(" ".join(cells))
    for eval_type in sorted(EVALUATION_TYPES, key=len, reverse=True):
        if re.search(
            rf"(?<![A-Za-z가-힣]){re.escape(eval_type)}(?![A-Za-z가-힣])",
            combined,
        ):
            return eval_type
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


def infer_evaluation_types_from_column(
    cells: list[str],
    header_cells: list[str] | None,
) -> list[str]:
    """종류 열에 '본 정기'처럼 복수 값이 있으면 순서대로 반환한다."""
    type_index = find_header_column_index(header_cells, EVAL_TYPE_HEADER_NAMES)
    if type_index is None or type_index >= len(cells):
        return []

    cell = normalize_text(cells[type_index])
    if not cell:
        return []

    if cell in EVALUATION_TYPES:
        return [cell]

    found: list[str] = []
    for part in re.split(r"[\s/]+", cell):
        value = normalize_text(part)
        if value in EVALUATION_TYPES:
            found.append(value)
    return found


def ordered_rating_tokens_from_columns(
    cells: list[str],
    header_cells: list[str] | None,
) -> tuple[list[RatingToken], list[RatingToken]]:
    """현재등급·직전등급 열에서 순서대로 rating 토큰을 추출한다."""
    current_index = find_header_column_index(
        header_cells, CURRENT_RATING_HEADER_NAMES
    )
    previous_index = find_header_column_index(
        header_cells, PREVIOUS_RATING_HEADER_NAMES
    )

    current_tokens: list[RatingToken] = []
    if current_index is not None and current_index < len(cells):
        current_tokens = find_rating_tokens_in_text(cells[current_index])

    previous_tokens: list[RatingToken] = []
    if previous_index is not None and previous_index < len(cells):
        previous_tokens = find_rating_tokens_in_text(cells[previous_index])

    return current_tokens, previous_tokens


def rating_token_for_split_index(
    index: int,
    current_tokens: list[RatingToken],
    previous_tokens: list[RatingToken],
    *,
    orphan_tokens: list[RatingToken] | None = None,
) -> RatingToken | None:
    """merged row 분할 시 상품 index에 대응하는 등급 토큰을 고른다."""
    if index < len(current_tokens):
        return current_tokens[index]

    overflow_index = index - len(current_tokens)
    orphans = orphan_tokens or []
    if overflow_index < len(orphans):
        return orphans[overflow_index]
    if overflow_index < len(previous_tokens):
        return previous_tokens[overflow_index]
    if index < len(previous_tokens):
        return previous_tokens[index]

    # 현재·직전 열에 동일 단일 등급만 있을 때 merged 상품 전체에 공통 적용
    if (
        len(current_tokens) == 1
        and current_tokens[0]
        and (
            not previous_tokens
            or (
                len(previous_tokens) == 1
                and previous_tokens[0].rating == current_tokens[0].rating
                and previous_tokens[0].outlook == current_tokens[0].outlook
            )
        )
    ):
        return current_tokens[0]

    return None


def apply_rating_token_to_cells(
    cells: list[str],
    token: RatingToken,
    header_cells: list[str] | None,
) -> list[str]:
    """현재등급 열에 단일 rating 토큰만 남기도록 cells를 갱신한다."""
    current_index = find_header_column_index(
        header_cells, CURRENT_RATING_HEADER_NAMES
    )
    updated = list(cells)
    display = token.rating_display
    if current_index is not None:
        while len(updated) <= current_index:
            updated.append("")
        updated[current_index] = display
    return updated


def is_orphan_rating_row(row: ExtractedRatingRow) -> bool:
    """평가대상 없이 등급 토큰만 있는 primary 표 행."""
    if row.section != "primary_rating":
        return False

    label = normalize_text(row.raw_label)
    if not label or looks_like_instrument_label(label):
        return False

    if parse_rating_value(label):
        return True

    tokens = find_rating_tokens_in_text(label)
    if not tokens:
        return False

    from common.text_utils import normalize_label

    return normalize_label(label) == normalize_label(tokens[0].rating_display)


def is_evaluation_only_primary_row(row: ExtractedRatingRow) -> bool:
    """평가대상이 종류(본·정기 등)만 있고 상품명이 없는 primary 행."""
    if row.section != "primary_rating":
        return False
    label = normalize_text(row.raw_label)
    if label in EVALUATION_TYPES:
        return True
    target_index = find_header_column_index(
        row.header_cells, TARGET_LABEL_HEADER_NAMES
    )
    if target_index is None or target_index >= len(row.cells):
        return False
    target = normalize_text(row.cells[target_index])
    return not target and label in EVALUATION_TYPES


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

    distinct_ratings = {
        (item.token.rating, item.token.outlook) for item in candidates
    }
    if len(distinct_ratings) == 1:
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
        header_cells=list(header_cells) if header_cells else None,
    )
