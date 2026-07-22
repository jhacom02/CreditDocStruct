"""기간·단위 정규화 및 요약 재무지표."""

from __future__ import annotations

import re
from typing import Any

from common.matching_policy import normalize_metric_label
from extract.fin_tables import parse_numeric_cell, parse_period_header

_YEAR_ONLY_RE = re.compile(r"^(20\d{2})$")

NUM_FORMAT_INT = "#,##0"
NUM_FORMAT_DEC = "#,##0.0"


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


_SUMMARY_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "total_assets": (
        "총자산",
        "자산총계",
        "총자산(십억원)",
        "자산총계(억원)",
        "총자산(억원)",
    ),
    "net_income": ("당기순이익", "순이익", "당기순이익(십억원)", "당기순이익(억원)"),
    "total_borrowings": (
        "총차입금",
        "차입금",
        "차입부채",
        "총차입금(억원)",
    ),
    "bis_ratio": (
        "BIS자기자본비율",
        "BIS자본비율",
        "BIS기준총자본비율",
        "BIS기준 총자본비율",
        "BIS자기자본비율(%)",
        "BIS자본비율(%)",
    ),
    "liquidity_ratio": ("유동성비율", "유동성비율(%)"),
    "debt_ratio": (
        "부채비율",
        "부채비율(%)",
        "수정부채비율",
        "부채비율(별도기준)",
    ),
}

# 요약 금액 3행 (고정)
AMOUNT_ROW_SPECS: tuple[tuple[str, str], ...] = (
    ("총자산", "total_assets"),
    ("당기순이익", "net_income"),
    ("총차입금", "total_borrowings"),
)

# 비율 행: 표 라벨 우선순위 → 표시명
_RATIO_PRIORITY: tuple[tuple[str, str], ...] = (
    ("bis_ratio", "BIS자본비율(%)"),
    ("liquidity_ratio", "유동성비율(%)"),
    ("debt_ratio", "부채비율(%)"),
)


def _row_matches(raw_label: str, aliases: tuple[str, ...]) -> bool:
    compact = normalize_metric_label(raw_label)
    if not compact:
        return False
    for alias in aliases:
        alias_c = normalize_metric_label(alias)
        if not alias_c:
            continue
        if alias_c == compact:
            return True
        if alias_c in compact:
            return True
    return False


def _table_has_metric(table: dict[str, Any], metric_key: str) -> bool:
    aliases = _SUMMARY_LABEL_ALIASES.get(metric_key, ())
    for row in table.get("rows") or []:
        if not row:
            continue
        if _row_matches(str(row[0] or ""), aliases):
            return True
    return False


def resolve_ratio_row(table: dict[str, Any] | None) -> tuple[str, str]:
    """비율 행 (표시명, metric_key). BIS → 유동성 → 부채."""
    if table:
        for metric_key, display in _RATIO_PRIORITY:
            if _table_has_metric(table, metric_key):
                return display, metric_key
    return "부채비율(%)", "debt_ratio"


def build_summary_row_specs(
    table: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """요약 4행: 금액 3 + 동적 비율 1."""
    rows = list(AMOUNT_ROW_SPECS)
    display, key = resolve_ratio_row(table)
    rows.append((display, key))
    return rows


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
    """(값, raw 문자열). 환산 없음."""
    headers = list(table.get("headers") or [])
    period_cols: dict[str, int] = {}
    for index, header in enumerate(headers):
        norm = normalize_period_label(header)
        if norm:
            period_cols[norm] = index
    col = period_cols.get(period)
    if col is None:
        return None, None

    aliases = _SUMMARY_LABEL_ALIASES.get(metric_key, ())
    for row in table.get("rows") or []:
        if not row:
            continue
        label = str(row[0] or "")
        if not _row_matches(label, aliases):
            continue
        if col >= len(row):
            return None, None
        raw_cell = row[col]
        value, raw = parse_numeric_cell(raw_cell if raw_cell is not None else None)
        return value, raw if raw is not None else (
            str(raw_cell) if raw_cell is not None else None
        )
    return None, None


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


# 하위 호환: 테스트/구코드
def format_summary_unit_caption() -> str:
    return "(단위:억,%)"


def convert_to_eok(value: float | None, unit_token: str) -> float | None:
    """Deprecated: 환산 없음. 값 그대로 반환."""
    return value


SUMMARY_ROW_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("총자산", "total_assets", False),
    ("당기순이익", "net_income", False),
    ("총차입금", "total_borrowings", False),
    ("부채비율(%)", "debt_ratio", False),
)
