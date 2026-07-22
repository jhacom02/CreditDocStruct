"""기업별 신평사 select-and-judge.

기업 시트용 PDF 1건 선택:
1) usable financial_tables 후보 최우선
2) 그 안에서 NICE > KIS > KR
3) usable 재무가 없으면 등급 success 후보만으로 동일 agency 순위
"""

from __future__ import annotations

import re
from typing import Any

from agency.agency import normalize_agency_key
from common.text_utils import normalize_text
from export.fin_excel_utils import normalize_period_label

_AGENCY_RANK: dict[str, int] = {
    "nice": 0,
    "kis": 1,
    "kr": 2,
}

_MIN_LABELED_ROWS = 3
_MIN_PERIOD_COLS = 2


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
    # 빈 칸이 많은 깨진 헤더(한전 KIS 등) 제외
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


def _success_products(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        p
        for p in (result.get("products") or [])
        if p.get("status") == "success" and p.get("rating")
    ]


def select_result_for_company(
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """동일 기업 후보 중 1건 선택.

    usable 재무가 1차 기준이고, agency 순위(NICE>KIS>KR)는
    동일 풀 안에서의 순위다.
    """
    with_fin = [item for item in candidates if is_usable_financial(item)]
    pool = with_fin or [
        item for item in candidates if _success_products(item)
    ]
    if not pool:
        return None

    pool.sort(key=lambda item: agency_rank(item.get("agency")))
    return pool[0]


def select_one_per_company(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """기업당 1건. 등장 순서 유지."""
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

    selected: list[dict[str, Any]] = []
    for key in order:
        chosen = select_result_for_company(groups[key])
        if chosen is not None:
            selected.append(chosen)
    return selected
