"""merged 평가 행 복원 — YAML longest-match 기반 분할."""

from __future__ import annotations

from dataclasses import replace

from common.models import ExtractedRatingRow
from common.rating_tokens import RatingToken
from common.settings import InstrumentsConfig
from common.text_utils import normalize_label, normalize_text
from extract.label_fields import decompose_label_fields
from extract.row_parser import (
    EVALUATION_TYPES,
    apply_rating_token_to_cells,
    infer_evaluation_types_from_column,
    is_evaluation_only_primary_row,
    is_orphan_rating_row,
    ordered_rating_tokens_from_columns,
    rating_token_for_split_index,
)

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


def _evaluation_type_after_first_span(
    label_source: str,
    spans: list[tuple[int, int, str, str]],
) -> str | None:
    if not spans:
        return None

    compact = normalize_label(label_source)
    _start, end, _normalized, _key = spans[0]
    remainder = compact[end:]
    for eval_type in ("본평가", "본"):
        if remainder.startswith(normalize_label(eval_type)):
            return "본평가" if eval_type == "본평가" else "본"
    return None


def _apply_split_rating(
    row: ExtractedRatingRow,
    token: RatingToken,
) -> ExtractedRatingRow:
    cells = apply_rating_token_to_cells(row.cells, token, row.header_cells)
    return replace(
        row,
        cells=cells,
        rating=token.rating,
        outlook=token.outlook,
        raw_outlook=token.raw_outlook,
        rating_status="single",
        rating_cells=[token.rating_display],
    )


def split_merged_row(
    row: ExtractedRatingRow,
    config: InstrumentsConfig,
    *,
    orphan_tokens: list[RatingToken] | None = None,
) -> list[ExtractedRatingRow]:
    """merged 라벨을 상품별 ExtractedRatingRow로 분할하고 등급을 1:1 매핑한다."""
    label_source = row.label_text or row.raw_label or " ".join(row.cells)
    spans = find_registered_label_spans(label_source, config)
    if len({item[3] for item in spans}) < 2:
        return [row]

    labels = _split_text_by_spans(label_source, spans)
    current_tokens, previous_tokens = ordered_rating_tokens_from_columns(
        row.cells, row.header_cells
    )
    inherited_eval = row.evaluation_type or _evaluation_type_after_first_span(
        label_source, spans
    )
    eval_types = infer_evaluation_types_from_column(row.cells, row.header_cells)

    rebuilt: list[ExtractedRatingRow] = []
    child_index = 0
    for label in labels:
        if label in EVALUATION_ONLY_LABELS:
            continue

        child = replace(
            row,
            raw_label=label,
            label_text=label,
            row_index=row.row_index + child_index,
        )
        if child_index < len(eval_types):
            child = replace(child, evaluation_type=eval_types[child_index])
        elif child_index == 0 and inherited_eval in EVALUATION_ONLY_LABELS:
            child = replace(child, evaluation_type=inherited_eval)

        token = rating_token_for_split_index(
            child_index,
            current_tokens,
            previous_tokens,
            orphan_tokens=orphan_tokens,
        )
        if token is not None:
            child = _apply_split_rating(child, token)
        else:
            child = replace(
                child,
                rating=None,
                outlook=None,
                raw_outlook=None,
                rating_status="none",
                rating_cells=[],
            )

        rebuilt.append(child)
        child_index += 1

    return rebuilt or [row]


def _is_bon_only_label(row: ExtractedRatingRow) -> bool:
    return is_evaluation_only_primary_row(row)


def is_collapsed_rating_fields(row: ExtractedRatingRow) -> bool:
    """종류·현재등급 셀에 복수 평가/등급이 공백으로 붙은 붕괴 행인지."""
    eval_types = infer_evaluation_types_from_column(
        row.cells, row.header_cells
    )
    current_tokens, _previous = ordered_rating_tokens_from_columns(
        row.cells, row.header_cells
    )
    return len(eval_types) >= 2 and len(current_tokens) >= 2


def _collect_orphan_tokens(
    rows: list[ExtractedRatingRow],
    start_index: int,
) -> tuple[list[RatingToken], int]:
    from common.rating_tokens import find_rating_tokens_in_text

    tokens: list[RatingToken] = []
    index = start_index
    while index < len(rows) and is_orphan_rating_row(rows[index]):
        tokens.extend(find_rating_tokens_in_text(rows[index].raw_label))
        index += 1
    return tokens, index


def rebuild_merged_rows(
    rows: list[ExtractedRatingRow],
    config: InstrumentsConfig,
) -> tuple[list[ExtractedRatingRow], str | None]:
    """분류 전 merged 행을 복원한다. 복원 불가 시 오류 메시지를 반환."""
    rebuilt: list[ExtractedRatingRow] = []
    index = 0

    while index < len(rows):
        row = rows[index]

        if is_orphan_rating_row(row):
            index += 1
            continue

        decomposed = decompose_label_fields(
            row,
            header_cells=row.header_cells,
            config=config,
        )

        if _is_bon_only_label(decomposed):
            index += 1
            continue

        if "@" in normalize_text(decomposed.raw_label):
            index += 1
            continue

        label_text = decomposed.label_text or decomposed.raw_label
        label_spans = find_registered_label_spans(label_text, config)
        multi_label = len({item[3] for item in label_spans}) >= 2
        collapsed = is_collapsed_rating_fields(decomposed)

        # 라벨 없이 종류/등급만 붕괴된 primary는 복원 불가 → 스킵
        # (유효등급 섹션에서 상품을 가져오는 경우가 일반적)
        if collapsed and not multi_label and not normalize_text(label_text):
            index += 1
            continue

        merged = multi_label or is_merged_label_suspect(
            decomposed.raw_label, config
        )
        if (
            decomposed.source == "visual_layout"
            and decomposed.rating_status == "single"
        ):
            # visual 한 줄에는 평가대상 뒤의 종목명이 함께 붙는다.
            # 종목명에 등록 alias가 있어도 단일 등급 행이면 별도 상품이 아니다.
            merged = False

        # 복수 상품 라벨 + 붕괴된 종류/등급 → 분할 복원
        if collapsed and multi_label:
            merged = True

        if merged:
            orphan_tokens, next_index = _collect_orphan_tokens(rows, index + 1)
            split_rows = split_merged_row(
                decomposed,
                config,
                orphan_tokens=orphan_tokens,
            )
            if len(split_rows) <= 1:
                return [], "merged_row_rebuild_failed"
            rebuilt.extend(split_rows)
            index = next_index
            continue

        rebuilt.append(decomposed)
        index += 1

    if not rebuilt:
        return [], "no_valid_rows"

    return rebuilt, None
