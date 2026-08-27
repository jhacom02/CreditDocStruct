"""기업 시트 신용등급(요약) cascade."""

from __future__ import annotations

from typing import Any

from common.matching_policy import normalize_label
from common.settings import InstrumentsConfig
from export.agency_select import AGENCY_ORDER, pick_result_by_agency, success_products


def _product_union_key(product: dict[str, Any]) -> str:
    instrument_key = product.get("instrument_key")
    if instrument_key:
        return f"key:{instrument_key}"
    raw = product.get("raw_label") or product.get("normalized_label") or ""
    normalized = normalize_label(str(raw))
    return f"label:{normalized or raw}"


def _display_name_for_product(
    product: dict[str, Any],
    config: InstrumentsConfig,
) -> str:
    key = product.get("instrument_key")
    if key and key in config.instruments:
        return config.instruments[key].display_name
    if product.get("raw_label"):
        return str(product.get("raw_label"))
    return str(product.get("normalized_label") or "")


def _instrument_sort_index(
    union_key: str,
    config: InstrumentsConfig,
) -> tuple[int, str]:
    if union_key.startswith("key:"):
        instrument_key = union_key[4:]
        keys = list(config.instruments.keys())
        if instrument_key in keys:
            return (keys.index(instrument_key), "")
        return (len(keys), instrument_key)
    label = union_key[6:] if union_key.startswith("label:") else union_key
    return (len(config.instruments) + 1, label)


def build_cascaded_rating_rows(
    company_results: list[dict[str, Any]],
    config: InstrumentsConfig,
) -> list[tuple[str, str]]:
    """상품별 NICE → KIS → KR cascade. (표시명, 등급)."""
    by_agency = {
        agency: pick_result_by_agency(company_results, agency)
        for agency in AGENCY_ORDER
    }

    union_keys: dict[str, str] = {}
    for agency in AGENCY_ORDER:
        result = by_agency[agency]
        if result is None:
            continue
        for product in success_products(result):
            pk = _product_union_key(product)
            if pk not in union_keys:
                union_keys[pk] = _display_name_for_product(product, config)

    ordered_keys = sorted(
        union_keys.keys(),
        key=lambda pk: _instrument_sort_index(pk, config),
    )

    rows: list[tuple[str, str]] = []
    for pk in ordered_keys:
        rating: str | None = None
        display = union_keys[pk]
        for agency in AGENCY_ORDER:
            result = by_agency[agency]
            if result is None:
                continue
            for product in success_products(result):
                if _product_union_key(product) != pk:
                    continue
                if product.get("rating"):
                    rating = str(product["rating"])
                    display = _display_name_for_product(product, config)
                    break
            if rating:
                break
        if rating:
            rows.append((display, rating))
    return rows
