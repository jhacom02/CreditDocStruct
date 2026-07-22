"""재무지표 라벨 → metric_key exact match 분류기."""

from __future__ import annotations

from pathlib import Path

from common.matching_policy import normalize_metric_label
from common.models import ClassificationStatus
from common.settings import (
    MetricsConfig,
    get_metrics_config,
    load_metrics_config,
)


class MetricClassifier:
    """YAML metric_label_dictionary exact-match 분류기."""

    def __init__(self, config: MetricsConfig):
        self.config = config

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> MetricClassifier:
        if path is None:
            return cls(get_metrics_config())
        return cls(load_metrics_config(Path(path)))

    def classify_label(
        self, raw_label: str
    ) -> tuple[str | None, str, ClassificationStatus]:
        normalized = normalize_metric_label(raw_label)
        if not normalized:
            return None, "", "undefined"
        metric_key = self.config.normalized_lookup.get(normalized)
        if metric_key is not None:
            return metric_key, normalized, "matched"
        return None, normalized, "undefined"

    def display_name(self, metric_key: str | None) -> str:
        if not metric_key:
            return ""
        definition = self.config.metrics.get(metric_key)
        return definition.display_name if definition else metric_key

    def value_type(self, metric_key: str | None) -> str:
        if not metric_key:
            return "unknown"
        definition = self.config.metrics.get(metric_key)
        return definition.value_type if definition else "unknown"
