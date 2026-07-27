"""재무지표 8키 코드 카탈로그 (exact match)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from common.matching_policy import normalize_metric_label


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    display_name: str
    value_type: str = "unknown"


# 요약·facts 공통 8키
METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "total_assets": MetricDefinition(
        "total_assets", "총자산", "currency"
    ),
    "net_income": MetricDefinition(
        "net_income", "당기순이익", "currency"
    ),
    "total_borrowings": MetricDefinition(
        "total_borrowings", "총차입금", "currency"
    ),
    "equity": MetricDefinition("equity", "자기자본", "currency"),
    "debt_ratio": MetricDefinition(
        "debt_ratio", "부채비율(%)", "percent"
    ),
    "bis_ratio": MetricDefinition(
        "bis_ratio", "BIS자본비율(%)", "percent"
    ),
    "liquidity_ratio": MetricDefinition(
        "liquidity_ratio", "유동성비율(%)", "percent"
    ),
    "leverage": MetricDefinition(
        "leverage", "총자산/자기자본(배)", "ratio"
    ),
}

METRIC_DISPLAY_NAMES: dict[str, str] = {
    key: spec.display_name for key, spec in METRIC_DEFINITIONS.items()
}

_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "total_assets": ("총자산", "자산총계"),
    "net_income": ("당기순이익",),
    "total_borrowings": ("총차입금", "차입금", "차입부채"),
    "equity": ("자기자본", "자본총계"),
    "debt_ratio": ("부채비율", "수정부채비율", "부채비율(별도기준)"),
    "bis_ratio": (
        "BIS자기자본비율",
        "BIS자본비율",
        "BIS기준총자본비율",
        "BIS기준 총자본비율",
    ),
    "liquidity_ratio": ("유동성비율",),
    "leverage": ("총자산/자기자본", "레버리지배율"),
}


@dataclass(frozen=True)
class MetricLabelEntry:
    raw_label: str
    metric_key: str
    active: bool = True
    note: str = ""


@dataclass(frozen=True)
class MetricsConfig:
    metrics: dict[str, MetricDefinition]
    metric_label_dictionary: tuple[MetricLabelEntry, ...]
    normalized_lookup: dict[str, str]


def _build_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for metric_key, aliases in _METRIC_ALIASES.items():
        for alias in aliases:
            normalized = normalize_metric_label(alias)
            if not normalized:
                continue
            existing = lookup.get(normalized)
            if existing is not None and existing != metric_key:
                raise ValueError(
                    f"metric alias conflict {normalized!r}: "
                    f"{existing!r} vs {metric_key!r}"
                )
            lookup[normalized] = metric_key
    return lookup


@lru_cache(maxsize=1)
def get_metrics_config() -> MetricsConfig:
    lookup = _build_lookup()
    entries = tuple(
        MetricLabelEntry(raw_label=alias, metric_key=key)
        for key, aliases in _METRIC_ALIASES.items()
        for alias in aliases
    )
    return MetricsConfig(
        metrics=dict(METRIC_DEFINITIONS),
        metric_label_dictionary=entries,
        normalized_lookup=lookup,
    )


def clear_metrics_config_cache() -> None:
    get_metrics_config.cache_clear()


def display_name_for(metric_key: str | None) -> str:
    if not metric_key:
        return ""
    return METRIC_DISPLAY_NAMES.get(metric_key, metric_key)
