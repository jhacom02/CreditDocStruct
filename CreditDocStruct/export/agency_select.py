"""기업별 PDF 그룹핑 · 신평사별 선택 · 재무 usable 판정."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from agency.agency import AGENCY_DISPLAY_NAMES, normalize_agency_key
from common.text_utils import normalize_text
from export.fin_excel_utils import normalize_period_label

AGENCY_ORDER: tuple[str, ...] = ("nice", "kis", "kr")

RATING_RAW_SECTION_TITLE = "신용등급(원본)"
FIN_RAW_SECTION_TITLE = "재무지표(원본)"


def agency_display_name(agency_key: str) -> str:
    """Excel raw 소제목용 신평사명 (NICE신용평가㈜ 등)."""
    return AGENCY_DISPLAY_NAMES.get(agency_key, agency_key)

_AGENCY_RANK: dict[str, int] = {
    "nice": 0,
    "kis": 1,
    "kr": 2,
}

_MIN_LABELED_ROWS = 3
_MIN_PERIOD_COLS = 2

_EVAL_DATE_RE = re.compile(
    r"(?P<year>20\d{2})\s*[.\-/]\s*(?P<month>\d{1,2})\s*[.\-/]\s*(?P<day>\d{1,2})"
)


def company_group_key(name: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(name)).lower()


def agency_rank(agency: str | None) -> int:
    key = normalize_agency_key(agency)
    if key is None:
        return 9
    return _AGENCY_RANK.get(key, 9)


def is_usable_financial_table(table: dict[str, Any]) -> bool:
    """기간열≥2, 데이터 헤더의 절반 이상이 기간, 라벨 있는 데이터 행≥3."""
    headers = list(table.get("headers") or [])
    data_headers = headers[1:] if len(headers) > 1 else list(headers)
    if not data_headers:
        return False
    period_count = sum(
        1 for header in data_headers if normalize_period_label(header)
    )
    if period_count < _MIN_PERIOD_COLS:
        return False
    if period_count < len(data_headers) * 0.5:
        return False

    labeled_rows = 0
    for row in table.get("rows") or []:
        if not row:
            continue
        if str(row[0] or "").strip():
            labeled_rows += 1
    return labeled_rows >= _MIN_LABELED_ROWS


def is_usable_financial(result: dict[str, Any]) -> bool:
    tables = result.get("financial_tables") or []
    return any(is_usable_financial_table(t) for t in tables)


def success_products(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        p
        for p in (result.get("products") or [])
        if p.get("status") == "success" and p.get("rating")
    ]


def _parse_evaluation_date(text: str | None) -> date | None:
    if not text:
        return None
    match = _EVAL_DATE_RE.search(normalize_text(text))
    if not match:
        return None
    try:
        return date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return None


def latest_evaluation_date(candidates: list[dict[str, Any]]) -> str:
    """그룹 내 가장 최신 evaluation_date 문자열 (원문 형식 유지)."""
    best_date: date | None = None
    best_text = ""
    for item in candidates:
        raw = item.get("evaluation_date") or ""
        parsed = _parse_evaluation_date(raw)
        if parsed is None:
            continue
        if best_date is None or parsed > best_date:
            best_date = parsed
            best_text = str(raw)
    return best_text


def group_results_by_company(
    results: list[dict[str, Any]],
) -> tuple[list[str], dict[str, list[dict[str, Any]]]]:
    """등장 순서 + 기업키 → PDF 목록."""
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for result in results:
        key = company_group_key(result.get("company_name"))
        if not key:
            key = company_group_key(result.get("file_name")) or f"anon_{id(result)}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(result)
    return order, groups


def pick_result_by_agency(
    candidates: list[dict[str, Any]],
    agency_key: str,
) -> dict[str, Any] | None:
    """신평사별 대표 PDF — success product 수 우선."""
    pool = [
        item
        for item in candidates
        if normalize_agency_key(item.get("agency")) == agency_key
        and success_products(item)
    ]
    if not pool:
        return None
    pool.sort(
        key=lambda item: (
            -len(success_products(item)),
            agency_rank(item.get("agency")),
        )
    )
    return pool[0]


def pick_usable_financial_table(
    result: dict[str, Any],
) -> dict[str, Any] | None:
    for table in result.get("financial_tables") or []:
        if is_usable_financial_table(table):
            return table
    return None


def iter_usable_fin_by_agency(
    candidates: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """(agency_key, result, table) — AGENCY_ORDER 순, usable만."""
    picked: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for agency_key in AGENCY_ORDER:
        pool = [
            item
            for item in candidates
            if normalize_agency_key(item.get("agency")) == agency_key
            and is_usable_financial(item)
        ]
        if not pool:
            continue
        pool.sort(key=lambda item: agency_rank(item.get("agency")))
        result = pool[0]
        table = pick_usable_financial_table(result)
        if table is not None:
            picked.append((agency_key, result, table))
    return picked


def select_result_for_company(
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """하위 호환: 대표 1 PDF (usable 재무 우선, NICE > KIS > KR)."""
    with_fin = [item for item in candidates if is_usable_financial(item)]
    pool = with_fin or [item for item in candidates if success_products(item)]
    if not pool:
        return None
    pool.sort(key=lambda item: agency_rank(item.get("agency")))
    return pool[0]


def select_one_per_company(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """기업당 1건. 등장 순서 유지 (목록/트리거용)."""
    order, groups = group_results_by_company(results)
    selected: list[dict[str, Any]] = []
    for key in order:
        chosen = select_result_for_company(groups[key])
        if chosen is not None:
            selected.append(chosen)
    return selected
