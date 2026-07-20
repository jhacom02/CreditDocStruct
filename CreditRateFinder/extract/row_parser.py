"""셀/줄 → ExtractedRatingRow 조립 (현재등급 열 선택·rating_status 판정).

분류(exact match)는 classify에 위임한다. 이 모듈은 rating_status만 확정한다.
"""

from __future__ import annotations

import re

from common.models import ExtractedRatingRow
from common.rating_tokens import (
    OUTLOOK_TOKEN_RE,
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

# selected 후보로 쓰는 평가 종류
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
EVAL_TYPE_HEADER_NAMES = ("종류", "평가종류", "구분")


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


def looks_like_rating_row(text: str | None) -> bool:
    """구조 게이트: 타입이 미지여도 평가 행 후보로 인정."""
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


def find_header_column_index(
    header_cells: list[str] | None,
    names: tuple[str, ...] = CURRENT_RATING_HEADER_NAMES,
) -> int | None:
    """헤더 셀에서 이름(공백 무시·대소문자 무시)이 포함된 열 인덱스를 찾는다."""
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
    """종류 열 또는 셀 목록에서 평가 종류를 추론한다."""
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
            if OUTLOOK_TOKEN_RE.fullmatch(cell) and not parse_rating_value(cell):
                continue
            rating_cells.append(cell)
    return rating_cells


def _resolve_single_rating(
    rating_cell: str,
    cleaned_values: list[str],
) -> tuple[str, str | None] | None:
    tokens = find_rating_tokens_in_text(rating_cell)
    if len(tokens) != 1:
        return None

    rating = tokens[0].rating
    outlook = tokens[0].outlook
    try:
        cell_index = cleaned_values.index(rating_cell)
    except ValueError:
        cell_index = -1

    if outlook is None and 0 <= cell_index < len(cleaned_values) - 1:
        next_cell = cleaned_values[cell_index + 1]
        outlook_match = OUTLOOK_TOKEN_RE.fullmatch(next_cell)
        if outlook_match:
            outlook = normalize_outlook(outlook_match.group("outlook"))

    return rating, outlook


def _pick_current_rating_cell(
    cells: list[str],
    *,
    header_cells: list[str] | None,
    current_rating_cell: str | None,
) -> str | None:
    if current_rating_cell is not None and normalize_text(current_rating_cell):
        return normalize_text(current_rating_cell)

    index = find_header_column_index(header_cells, CURRENT_RATING_HEADER_NAMES)
    if index is not None and index < len(cells):
        value = normalize_text(cells[index])
        return value or None
    return None


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
    """셀/줄 값 목록 → ExtractedRatingRow.

    rating 셀 0개 → none
    rating 셀 1개 + 셀 내부 토큰 1개 → single
    rating 셀 2개 이상 → 현재등급 열/셀로 재해석, 실패 시 ambiguous
    """
    # 헤더 정렬 행은 빈 문자열을 유지해야 열 인덱스가 맞다.
    if header_cells is not None and len(values) == len(header_cells):
        cells = [normalize_text(value) for value in values]
        cleaned_values = [value for value in cells if value]
    else:
        cleaned_values = [
            normalize_text(value) for value in values if normalize_text(value)
        ]
        cells = cleaned_values

    if not cleaned_values and not any(cells):
        return None

    rating_cells = _collect_rating_cells(
        cells if any(cells) else cleaned_values
    )
    scan_values = cells if any(cells) else cleaned_values

    rating: str | None = None
    outlook: str | None = None
    rating_status: str

    if not rating_cells:
        rating_status = "none"
    elif (
        len(rating_cells) == 1
        and count_rating_tokens_in_cell(rating_cells[0]) == 1
    ):
        resolved = _resolve_single_rating(rating_cells[0], scan_values)
        if resolved is None:
            rating_status = "ambiguous"
        else:
            rating_status = "single"
            rating, outlook = resolved
    else:
        # 복수 등급 셀 또는 셀 내부 복수 토큰 → 현재등급 열만 재파싱
        current_cell = _pick_current_rating_cell(
            scan_values,
            header_cells=header_cells,
            current_rating_cell=current_rating_cell,
        )
        if current_cell is None:
            rating_status = "ambiguous"
        else:
            tokens = find_rating_tokens_in_text(current_cell)
            if len(tokens) == 1:
                resolved = _resolve_single_rating(current_cell, scan_values)
                if resolved is None:
                    rating_status = "ambiguous"
                else:
                    rating_status = "single"
                    rating, outlook = resolved
            else:
                rating_status = "ambiguous"

    evaluation_type = infer_evaluation_type(scan_values, header_cells)
    raw_label = infer_raw_label(cleaned_values if cleaned_values else scan_values)

    if rating_status == "none" and not raw_label:
        return None
    if rating_status == "none" and not looks_like_instrument_label(raw_label):
        if not looks_like_rating_row(" ".join(cleaned_values or scan_values)):
            return None

    return ExtractedRatingRow(
        raw_label=raw_label,
        rating_cells=rating_cells,
        rating_status=rating_status,  # type: ignore[arg-type]
        rating=rating,
        outlook=outlook,
        page=page_number,
        row_index=row_index,
        section=section,
        source=source,
        cells=scan_values,
        evaluation_type=evaluation_type,
    )
