"""ExtractedFinTable → FinancialFact 정규화."""

from __future__ import annotations

from classify.metric_classifier import MetricClassifier
from common.models import ExtractedFinTable, FinancialFact, MetricValueType
from extract.fin_tables import (
    infer_unit_from_label,
    parse_numeric_cell,
    parse_period_header,
    strip_footnote_marker,
)


def _resolve_unit(
    *,
    label_unit: str | None,
    caption: str | None,
    value_type: str,
) -> str | None:
    if label_unit:
        return label_unit
    if value_type == "percent":
        return "percent"
    if value_type == "ratio":
        return "ratio"
    if caption:
        compact = caption.replace(" ", "")
        if "십억원" in compact:
            return "십억원"
        if "억원" in compact:
            return "억원"
        if "백만원" in compact:
            return "백만원"
        if "%" in compact:
            return "percent"
    return None


def facts_from_fin_table(
    table: ExtractedFinTable,
    classifier: MetricClassifier,
) -> tuple[list[FinancialFact], list[dict[str, str]]]:
    """표 1개 → facts + undefined 라벨 목록."""
    period_cols: list[tuple[int, str | None, int | None, int | None]] = []
    for col_index, header in enumerate(table.headers):
        period, year, month = parse_period_header(header)
        if period is not None:
            period_cols.append((col_index, period, year, month))

    # 기간이 없으면 숫자 열을 그대로 period=header 로 취급 (구분 열 제외)
    if not period_cols and len(table.headers) >= 2:
        for col_index, header in enumerate(table.headers[1:], start=1):
            period_cols.append((col_index, header or None, None, None))

    facts: list[FinancialFact] = []
    undefined: list[dict[str, str]] = []
    seen_undefined: set[str] = set()

    for row_index, row in enumerate(table.rows):
        if not row:
            continue
        raw_label_cell = row[0] if row else ""
        cleaned_label, _mark = strip_footnote_marker(raw_label_cell)
        if not cleaned_label:
            continue
        # 적용재무제표처럼 텍스트만 있는 행도 포함
        metric_key, normalized, status = classifier.classify_label(
            cleaned_label
        )
        value_type_raw = classifier.value_type(metric_key)
        value_type: MetricValueType
        if value_type_raw in {"currency", "percent", "ratio", "text"}:
            value_type = value_type_raw  # type: ignore[assignment]
        else:
            value_type = "unknown"

        label_unit = infer_unit_from_label(cleaned_label)

        if status == "undefined" and normalized not in seen_undefined:
            seen_undefined.add(normalized)
            undefined.append(
                {
                    "raw_label": cleaned_label,
                    "normalized_label": normalized,
                }
            )

        for col_index, period, year, month in period_cols:
            if col_index >= len(row):
                continue
            cell_raw = row[col_index]
            if value_type == "text":
                value = None
                value_raw = cell_raw or None
            else:
                value, value_raw = parse_numeric_cell(cell_raw)

            unit = _resolve_unit(
                label_unit=label_unit,
                caption=table.unit_caption,
                value_type=value_type,
            )
            facts.append(
                FinancialFact(
                    metric_key=metric_key,
                    raw_label=cleaned_label,
                    normalized_label=normalized,
                    classification_status=status,
                    period=period,
                    period_year=year,
                    period_month=month,
                    value=value,
                    value_raw=value_raw,
                    unit=unit,
                    value_type=value_type,
                    basis=table.basis,
                    page=table.page,
                    row_index=row_index,
                    col_index=col_index,
                )
            )

    return facts, undefined


def facts_from_fin_tables(
    tables: list[ExtractedFinTable],
    classifier: MetricClassifier | None = None,
) -> tuple[list[FinancialFact], list[dict[str, str]]]:
    active = classifier or MetricClassifier.from_yaml()
    all_facts: list[FinancialFact] = []
    undefined: list[dict[str, str]] = []
    seen: set[str] = set()
    for table in tables:
        facts, undef = facts_from_fin_table(table, active)
        all_facts.extend(facts)
        for item in undef:
            key = item["normalized_label"]
            if key in seen:
                continue
            seen.add(key)
            undefined.append(item)
    return all_facts, undefined
