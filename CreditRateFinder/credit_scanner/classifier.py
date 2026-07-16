from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from credit_scanner.text_utils import compact_text, normalize_text

DEFAULT_TAXONOMY_PATH = (
    Path(__file__).resolve().parent / "config" / "instrument_taxonomy.yaml"
)


@dataclass(frozen=True)
class ClassificationResult:
    instrument_type: str
    raw_label: str | None
    confidence: float
    status: str  # matched | unknown | ambiguous
    matched_alias: str | None = None
    score: float = 0.0
    features: tuple[str, ...] = ()
    runner_up: str | None = None


class InstrumentClassifier:
    """외부 taxonomy 기반 점수형 평가대상 분류기."""

    def __init__(self, taxonomy: dict[str, Any]):
        self.min_score = float(taxonomy.get("min_score", 8))
        self.ambiguity_margin = float(taxonomy.get("ambiguity_margin", 2))

        self.feature_patterns: dict[str, list[re.Pattern[str]]] = {}
        for name, patterns in (taxonomy.get("features") or {}).items():
            self.feature_patterns[name] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

        self.instruments: dict[str, dict[str, Any]] = (
            taxonomy.get("instruments") or {}
        )

        self._alias_rules: list[tuple[str, str, re.Pattern[str]]] = []
        for instrument_type, spec in self.instruments.items():
            for alias in spec.get("aliases") or []:
                compact_alias = compact_text(alias)
                if not compact_alias:
                    continue
                pattern = re.compile(re.escape(compact_alias), re.IGNORECASE)
                self._alias_rules.append((instrument_type, alias, pattern))

        self._alias_rules.sort(key=lambda item: len(item[1]), reverse=True)

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> InstrumentClassifier:
        taxonomy_path = Path(path) if path else DEFAULT_TAXONOMY_PATH
        with taxonomy_path.open(encoding="utf-8") as handle:
            taxonomy = yaml.safe_load(handle)
        return cls(taxonomy)

    def extract_features(self, text: str) -> set[str]:
        normalized = normalize_text(text)
        found: set[str] = set()

        for name, patterns in self.feature_patterns.items():
            if any(pattern.search(normalized) for pattern in patterns):
                found.add(name)

        return found

    def _alias_match(self, text: str) -> tuple[str | None, str | None]:
        compact = compact_text(text)

        for instrument_type, alias, pattern in self._alias_rules:
            if pattern.search(compact):
                return instrument_type, alias

        return None, None

    def _score_instrument(
        self,
        instrument_type: str,
        features: set[str],
        alias_hit: str | None,
    ) -> float:
        spec = self.instruments[instrument_type]
        score = 0.0

        if alias_hit == instrument_type:
            score += 20.0

        score += float(spec.get("base_score", 0))

        for feature in spec.get("boost_features") or []:
            if feature in features:
                score += 5.0

        require_any = set(spec.get("require_any") or [])
        if require_any and features.isdisjoint(require_any):
            if alias_hit != instrument_type:
                return 0.0

        for feature in spec.get("exclude_features") or []:
            if feature in features:
                score -= 12.0

        return score

    def classify(self, text: str | None) -> ClassificationResult:
        normalized = normalize_text(text)

        if not normalized:
            return ClassificationResult(
                instrument_type="unknown",
                raw_label=None,
                confidence=0.0,
                status="unknown",
            )

        features = self.extract_features(normalized)
        alias_type, matched_alias = self._alias_match(normalized)

        scores: dict[str, float] = {}
        for instrument_type in self.instruments:
            scores[instrument_type] = self._score_instrument(
                instrument_type=instrument_type,
                features=features,
                alias_hit=alias_type,
            )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_type, best_score = ranked[0]
        second_type, second_score = (
            ranked[1] if len(ranked) > 1 else (None, 0.0)
        )

        raw_label = matched_alias
        if raw_label is None:
            raw_label = normalized.split("\n")[0].strip()[:80] or normalized

        if best_score < self.min_score:
            return ClassificationResult(
                instrument_type="unknown",
                raw_label=raw_label,
                confidence=0.0,
                status="unknown",
                matched_alias=matched_alias,
                score=best_score,
                features=tuple(sorted(features)),
                runner_up=best_type if best_score > 0 else None,
            )

        if (
            second_type is not None
            and (best_score - second_score) < self.ambiguity_margin
            and second_score >= self.min_score
        ):
            return ClassificationResult(
                instrument_type="ambiguous",
                raw_label=raw_label,
                confidence=max(0.0, min(1.0, best_score / 40.0)),
                status="ambiguous",
                matched_alias=matched_alias,
                score=best_score,
                features=tuple(sorted(features)),
                runner_up=f"{best_type}|{second_type}",
            )

        confidence = max(0.35, min(1.0, best_score / 40.0))

        return ClassificationResult(
            instrument_type=best_type,
            raw_label=matched_alias or raw_label,
            confidence=confidence,
            status="matched",
            matched_alias=matched_alias,
            score=best_score,
            features=tuple(sorted(features)),
            runner_up=second_type,
        )

    def looks_like_instrument_row(self, text: str | None) -> bool:
        result = self.classify(text)
        if result.status == "matched":
            return True

        normalized = normalize_text(text)
        if not normalized:
            return False

        compact = compact_text(normalized)
        hints = (
            "등급",
            "사채",
            "채권",
            "증권",
            "어음",
            "발행자",
            "issuer",
            "rating",
            "coco",
            "abs",
            "cp",
            "보험",
        )
        return any(hint in compact for hint in hints)


@lru_cache(maxsize=4)
def get_classifier(taxonomy_path: str | None = None) -> InstrumentClassifier:
    return InstrumentClassifier.from_yaml(taxonomy_path)


def classify_instrument(
    text: str | None,
    taxonomy_path: str | None = None,
    classifier: InstrumentClassifier | None = None,
) -> str | None:
    active = classifier or get_classifier(taxonomy_path)
    result = active.classify(text)
    if result.status != "matched":
        return None
    return result.instrument_type
