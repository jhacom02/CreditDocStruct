"""재무지표 라벨 → metric_key exact match 분류기."""

from __future__ import annotations

from common.matching_policy import normalize_metric_label
from common.metric_catalog import MetricsConfig, get_metrics_config
from common.models import ClassificationStatus


class MetricClassifier:
    """코드 카탈로그 exact-match 분류기."""

    def __init__(self, config: MetricsConfig):
        self.config = config

    @classmethod
    def from_catalog(cls) -> MetricClassifier:
        return cls(get_metrics_config())

    # 하위 호환
    @classmethod
    def from_yaml(cls, path: object = None) -> MetricClassifier:
        del path
        return cls.from_catalog()

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
