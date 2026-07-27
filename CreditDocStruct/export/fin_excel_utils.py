"""기간·단위 정규화 및 요약 재무지표."""

from __future__ import annotations

import re
from typing import Any

from common.matching_policy import normalize_metric_label
from common.metric_catalog import (
    METRIC_DISPLAY_NAMES,
    get_metrics_config,
)
from extract.fin_tables import parse_numeric_cell, parse_period_header

_YEAR_ONLY_RE = re.compile(r"^(20\d{2})$")

NUM_FORMAT_INT = "#,##0"
NUM_FORMAT_DEC = "#,##0.0"

# 폴백 표시명 (매칭 실패 시)
_DEFAULT_ROW1 = "총자산"
_DEFAULT_ROW2 = "당기순이익"
_DEFAULT_ROW3 = "총차입금"
_DEFAULT_ROW4 = "부채비율(%)"


def normalize_period_label(text: str | None) -> str | None:
    """기간 헤더 → YYYY.MM. 연도만 있으면 .12."""
    period, year, month = parse_period_header(text)
    if period:
        return period
    normalized = (text or "").strip()
    match = _YEAR_ONLY_RE.match(re.sub(r"\s+", "", normalized))
    if match:
        return f"{match.group(1)}.12"
    return None


def normalize_currency_unit_token(unit_caption: str | None) -> str:
    """단위 캡션에서 화폐 단위 토큰만 정규화: 억/십억/백만."""
    text = (unit_caption or "").replace(" ", "")
    if "십억" in text:
        return "십억"
    if "백만" in text:
        return "백만"
    if "억" in text:
        return "억"
    return "십억"


def format_raw_unit_caption(unit_caption: str | None) -> str:
    """재무지표·요약 공통: (단위:십억,%)"""
    token = normalize_currency_unit_token(unit_caption)
    return f"(단위:{token},%)"


def infer_unit_caption_from_table(table: dict[str, Any]) -> str | None:
    """unit_caption이 없을 때 라벨에서 단위 추론."""
    caption = table.get("unit_caption")
    if caption:
        return str(caption)
    for row in table.get("rows") or []:
        if not row:
            continue
        label = str(row[0] or "").replace(" ", "")
        if "십억" in label:
            return "십억"
        if "백만" in label:
            return "백만"
        if "억" in label:
            return "억"
    return None


def shared_unit_caption(table: dict[str, Any] | None) -> str:
    """재무지표·요약이 공유하는 (단위:…) 문자열."""
    if not table:
        return format_raw_unit_caption(None)
    inferred = infer_unit_caption_from_table(table)
    return format_raw_unit_caption(inferred)


def excel_number_format(raw: Any) -> str:
    """raw에 소수점이 있으면 #,##0.0, 아니면 #,##0."""
    text = "" if raw is None else str(raw)
    if "." in text:
        return NUM_FORMAT_DEC
    return NUM_FORMAT_INT


def _index_table_by_metric(
    table: dict[str, Any] | None,
) -> dict[str, list[Any]]:
    """metric_key → 표 행 (exact normalize만)."""
    index: dict[str, list[Any]] = {}
    if not table:
        return index
    lookup = get_metrics_config().normalized_lookup
    for row in table.get("rows") or []:
        if not row:
            continue
        normalized = normalize_metric_label(str(row[0] or ""))
        if not normalized:
            continue
        key = lookup.get(normalized)
        if key is None:
            continue
        index.setdefault(key, list(row))
    return index


def _table_has_metric(table: dict[str, Any] | None, metric_key: str) -> bool:
    return metric_key in _index_table_by_metric(table)


def resolve_funding_row(table: dict[str, Any] | None) -> tuple[str, str]:
    """3행: 총차입금 → 자기자본 → 기본 총차입금."""
    if _table_has_metric(table, "total_borrowings"):
        return METRIC_DISPLAY_NAMES["total_borrowings"], "total_borrowings"
    if _table_has_metric(table, "equity"):
        return METRIC_DISPLAY_NAMES["equity"], "equity"
    return _DEFAULT_ROW3, "total_borrowings"


def resolve_ratio_row(table: dict[str, Any] | None) -> tuple[str, str]:
    """4행: 부채비율 → BIS → 유동성 → 레버리지 → 기본 부채비율(%)."""
    if _table_has_metric(table, "debt_ratio"):
        return METRIC_DISPLAY_NAMES["debt_ratio"], "debt_ratio"
    if _table_has_metric(table, "bis_ratio"):
        return METRIC_DISPLAY_NAMES["bis_ratio"], "bis_ratio"
    if _table_has_metric(table, "liquidity_ratio"):
        return METRIC_DISPLAY_NAMES["liquidity_ratio"], "liquidity_ratio"
    if _table_has_metric(table, "leverage"):
        return METRIC_DISPLAY_NAMES["leverage"], "leverage"
    return _DEFAULT_ROW4, "debt_ratio"


def build_summary_row_specs(
    table: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """요약 항상 4행: (표시명, metric_key)."""
    funding_display, funding_key = resolve_funding_row(table)
    ratio_display, ratio_key = resolve_ratio_row(table)
    return [
        (_DEFAULT_ROW1, "total_assets"),
        (_DEFAULT_ROW2, "net_income"),
        (funding_display, funding_key),
        (ratio_display, ratio_key),
    ]


def _row_values_for_periods(
    table: dict[str, Any],
    *,
    metric_key: str,
    periods: list[str],
) -> list[tuple[float | None, str | None]]:
    return [
        lookup_raw_value(table, metric_key=metric_key, period=period)
        for period in periods
    ]


def _row_has_any_value(values: list[tuple[float | None, str | None]]) -> bool:
    return any(item[0] is not None for item in values)


def cascade_summary_rows(
    tables_in_order: list[dict[str, Any] | None],
) -> tuple[list[str], str, list[tuple[str, str, list[tuple[float | None, str | None]]]]]:
    """NICE→KIS→KR usable 표에서 빈 행만 다음 표로 cascade.

    Returns (periods, unit_caption, [(display, metric_key, values), ...]).
    """
    tables = [table for table in tables_in_order if table]
    if not tables:
        specs = build_summary_row_specs(None)
        unit = shared_unit_caption(None)
        return [], unit, [(display, key, []) for display, key in specs]

    periods: list[str] = []
    unit = shared_unit_caption(None)
    for table in tables:
        candidate_periods = build_summary_periods(
            list((table.get("headers") or [])[1:])
        )
        if candidate_periods:
            periods = candidate_periods
            unit = shared_unit_caption(table)
            break
    if not periods:
        unit = shared_unit_caption(tables[0])

    slot_resolvers = (
        lambda t: (_DEFAULT_ROW1, "total_assets"),
        lambda t: (_DEFAULT_ROW2, "net_income"),
        resolve_funding_row,
        resolve_ratio_row,
    )

    output: list[tuple[str, str, list[tuple[float | None, str | None]]]] = []
    for resolver in slot_resolvers:
        display = ""
        metric_key = ""
        values: list[tuple[float | None, str | None]] = []
        filled = False
        for table in tables:
            display, metric_key = resolver(table)
            if not periods:
                continue
            values = _row_values_for_periods(
                table, metric_key=metric_key, periods=periods
            )
            if _row_has_any_value(values):
                filled = True
                break
        if not filled:
            display, metric_key = resolver(tables[0])
            values = [(None, None) for _ in periods] if periods else []
        output.append((display, metric_key, values))

    return periods, unit, output


def build_summary_periods(period_headers: list[str]) -> list[str]:
    """연말 우선 [Y-2.12, Y-1.12, latest]. 연말 열이 raw에 없으면 마지막 3기간."""
    normalized = [normalize_period_label(h) for h in period_headers]
    normalized = [p for p in normalized if p]
    if not normalized:
        return []
    latest = normalized[-1]
    year = int(latest.split(".")[0])
    year_ends = [f"{year - 2:04d}.12", f"{year - 1:04d}.12", latest]
    present = set(normalized)
    if year_ends[0] not in present or year_ends[1] not in present:
        return normalized[-3:] if len(normalized) >= 3 else list(normalized)
    return year_ends


def lookup_raw_value(
    table: dict[str, Any],
    *,
    metric_key: str,
    period: str,
) -> tuple[float | None, str | None]:
    """(값, raw 문자열). exact 키 인덱싱, 환산 없음."""
    headers = list(table.get("headers") or [])
    period_cols: dict[str, int] = {}
    for index, header in enumerate(headers):
        norm = normalize_period_label(header)
        if norm:
            period_cols[norm] = index
    col = period_cols.get(period)
    if col is None:
        return None, None

    row = _index_table_by_metric(table).get(metric_key)
    if row is None:
        return None, None
    if col >= len(row):
        return None, None
    raw_cell = row[col]
    value, raw = parse_numeric_cell(raw_cell if raw_cell is not None else None)
    return value, raw if raw is not None else (
        str(raw_cell) if raw_cell is not None else None
    )


def normalize_fin_table_headers(
    table: dict[str, Any],
) -> tuple[list[str], list[list[Any]]]:
    """헤더 기간 정규화 + 빈/비기간 열 제거 + 데이터 행렬."""
    headers = list(table.get("headers") or [])
    rows = [list(row) for row in (table.get("rows") or [])]
    if not headers:
        return [], rows

    keep: list[int] = [0]
    out_headers: list[str] = [str(headers[0] or "구분")]
    for index, header in enumerate(headers[1:], start=1):
        period = normalize_period_label(header)
        if not period:
            continue
        keep.append(index)
        out_headers.append(period)

    out_rows: list[list[Any]] = []
    for row in rows:
        out_rows.append([row[i] if i < len(row) else None for i in keep])
    return out_headers, out_rows


def format_summary_unit_caption() -> str:
    return "(단위:억,%)"


def convert_to_eok(value: float | None, unit_token: str) -> float | None:
    """Deprecated: 환산 없음. 값 그대로 반환."""
    return value


# 하위 호환
AMOUNT_ROW_SPECS: tuple[tuple[str, str], ...] = (
    ("총자산", "total_assets"),
    ("당기순이익", "net_income"),
    ("총차입금", "total_borrowings"),
)

SUMMARY_ROW_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("총자산", "total_assets", False),
    ("당기순이익", "net_income", False),
    ("총차입금", "total_borrowings", False),
    ("부채비율(%)", "debt_ratio", False),
)
