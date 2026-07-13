from __future__ import annotations

import re

from credit_scanner.classifier import (
    ClassificationResult,
    InstrumentClassifier,
    classify_instrument,
    get_classifier,
)
from credit_scanner.constants import (
    HEADER_NOISE_TOKENS,
    RATING_ACTIONS,
    REMARK_CANDIDATES,
)
from credit_scanner.models import RatingRecord
from credit_scanner.rating_tokens import (
    find_rating_tokens,
    parse_rating_value,
    tokenize_values,
)
from credit_scanner.text_utils import (
    compact_text,
    normalize_evaluation_type,
    normalize_text,
)


def looks_like_rating_row(
    text: str | None,
    classifier: InstrumentClassifier | None = None,
) -> bool:
    """구조 게이트: 타입이 미지여도 평가 행 후보로 인정."""
    normalized = normalize_text(text)
    if not normalized:
        return False

    if any(noise in compact_text(normalized) for noise in HEADER_NOISE_TOKENS):
        tokens = tokenize_values([normalized])
        if not find_rating_tokens(tokens):
            return False

    active = classifier or get_classifier()
    if active.looks_like_instrument_row(normalized):
        return True

    tokens = tokenize_values([normalized])
    return bool(find_rating_tokens(tokens)) and len(normalized) >= 4


def infer_label_from_values(
    cleaned_values: list[str],
    classification: ClassificationResult,
) -> str:
    if classification.raw_label:
        return normalize_text(classification.raw_label)

    for value in cleaned_values:
        normalized = normalize_text(value)
        if not normalized:
            continue
        if parse_rating_value(normalized):
            continue
        if normalize_evaluation_type(normalized):
            continue
        if normalized in RATING_ACTIONS:
            continue
        if any(
            header in compact_text(normalized)
            for header in HEADER_NOISE_TOKENS
        ):
            continue
        return normalized

    return normalize_text(" ".join(cleaned_values[:1])) or "unknown"


def parse_rating_row_values(
    values: list[str],
    agency: str,
    file_name: str,
    page_number: int,
    section: str,
    source: str,
    confidence: float,
    classifier: InstrumentClassifier | None = None,
) -> RatingRecord | None:
    cleaned_values = [
        normalize_text(value)
        for value in values
        if normalize_text(value)
    ]

    if not cleaned_values:
        return None

    raw_text = normalize_text(" ".join(cleaned_values))
    active = classifier or get_classifier()
    classification = active.classify(raw_text)

    tokens = tokenize_values(cleaned_values)

    evaluation_type: str | None = None
    evaluation_index: int | None = None

    for index, token in enumerate(tokens):
        normalized_type = normalize_evaluation_type(token)
        if normalized_type:
            evaluation_type = normalized_type
            evaluation_index = index
            break

    rating_tokens = find_rating_tokens(tokens)

    if evaluation_index is not None:
        rating_tokens_after_evaluation = [
            item for item in rating_tokens if item[0] > evaluation_index
        ]
    else:
        rating_tokens_after_evaluation = rating_tokens

    if not rating_tokens_after_evaluation:
        return None

    _, current = rating_tokens_after_evaluation[0]
    previous: dict[str, str | None] | None = None

    if len(rating_tokens_after_evaluation) >= 2:
        _, previous = rating_tokens_after_evaluation[1]

    rating_action: str | None = None
    for token in tokens:
        if normalize_text(token) in RATING_ACTIONS:
            rating_action = normalize_text(token)
            break

    remark: str | None = None
    for candidate in REMARK_CANDIDATES:
        if candidate in raw_text:
            remark = candidate
            break

    raw_label = infer_label_from_values(cleaned_values, classification)

    if classification.status == "matched":
        instrument_type = classification.instrument_type
        classification_status = "matched"
    elif classification.status == "ambiguous":
        instrument_type = "ambiguous"
        classification_status = "ambiguous"
    else:
        instrument_type = "unknown"
        classification_status = "unknown"

    excluded_parts = {
        normalize_text(raw_label),
        evaluation_type or "",
        current["rating_display"] or "",
        previous["rating_display"] if previous else "",
        rating_action or "",
        remark or "",
    }

    issue_name_candidates: list[str] = []

    for value in cleaned_values:
        normalized_value = normalize_text(value)

        if normalized_value in excluded_parts:
            continue
        if active.classify(normalized_value).status == "matched":
            continue
        if parse_rating_value(normalized_value):
            continue
        if normalize_evaluation_type(normalized_value):
            continue
        if normalized_value in RATING_ACTIONS:
            continue
        if any(
            header in compact_text(normalized_value)
            for header in HEADER_NOISE_TOKENS
        ):
            continue

        if len(normalized_value) >= 5 and (
            re.search(r"\d", normalized_value)
            or "조건부" in normalized_value
            or "사채" in normalized_value
            or "영구" in normalized_value
            or "은행" in normalized_value
        ):
            issue_name_candidates.append(normalized_value)

    issue_name = (
        normalize_text(" ".join(issue_name_candidates))
        if issue_name_candidates
        else None
    )

    adjusted_confidence = confidence
    if classification_status == "unknown":
        adjusted_confidence = min(confidence, 0.55)
    elif classification_status == "ambiguous":
        adjusted_confidence = min(confidence, 0.70)
    else:
        adjusted_confidence = min(
            1.0,
            confidence * (0.75 + 0.25 * classification.confidence),
        )

    return RatingRecord(
        agency=agency,
        file_name=file_name,
        page=page_number,
        section=section,
        source=source,
        raw_label=raw_label,
        instrument_type=instrument_type,
        evaluation_type=evaluation_type,
        current_rating=str(current["rating"]),
        current_outlook=current["outlook"],
        current_rating_display=str(current["rating_display"]),
        previous_rating=str(previous["rating"]) if previous else None,
        previous_outlook=previous["outlook"] if previous else None,
        previous_rating_display=(
            str(previous["rating_display"]) if previous else None
        ),
        rating_action=rating_action,
        remark=remark,
        issue_name=issue_name,
        raw_text=raw_text,
        confidence=adjusted_confidence,
        classification_status=classification_status,
        classification_score=classification.score,
        classification_features=(
            ",".join(classification.features) if classification.features else None
        ),
        classification_runner_up=classification.runner_up,
    )


# re-export for extractors that need the gate helper
__all__ = [
    "classify_instrument",
    "looks_like_rating_row",
    "parse_rating_row_values",
]
