"""라벨 정규화, label_dictionary exact match, RatingRecord 생성."""

from __future__ import annotations

from pathlib import Path

from common.models import ExtractedRatingRow, RatingRecord
from common.settings import (
    InstrumentsConfig,
    get_instruments_config,
    load_instruments_config,
)
from common.text_utils import normalize_label


class LabelClassifier:
    """YAML label_dictionary exact-match 분류기."""

    def __init__(self, config: InstrumentsConfig):
        self.config = config

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> LabelClassifier:
        if path is None:
            return cls(get_instruments_config())
        return cls(load_instruments_config(Path(path)))

    def classify_row(self, row: ExtractedRatingRow) -> RatingRecord:
        normalized = normalize_label(row.raw_label)
        instrument_key = None
        if normalized:
            instrument_key = self.config.normalized_lookup.get(normalized)

        if instrument_key is not None:
            return RatingRecord(
                raw_label=row.raw_label,
                normalized_label=normalized,
                instrument_key=instrument_key,
                classification_status="matched",
                rating=row.rating,
                outlook=row.outlook,
                raw_outlook=row.raw_outlook,
                rating_status=row.rating_status,
                page=row.page,
                row_index=row.row_index,
                section=row.section,
                source=row.source,
                evaluation_type=row.evaluation_type,
                issue_name=row.issue_name,
                remark=row.remark,
                label_text=row.label_text,
            )

        return RatingRecord(
            raw_label=row.raw_label,
            normalized_label=normalized,
            instrument_key=None,
            classification_status="undefined",
            rating=row.rating,
            outlook=row.outlook,
            raw_outlook=row.raw_outlook,
            rating_status=row.rating_status,
            page=row.page,
            row_index=row.row_index,
            section=row.section,
            source=row.source,
            evaluation_type=row.evaluation_type,
            issue_name=row.issue_name,
            remark=row.remark,
            label_text=row.label_text,
        )

    def classify_rows(
        self, rows: list[ExtractedRatingRow]
    ) -> list[RatingRecord]:
        return [self.classify_row(row) for row in rows]

    def classify_label(self, raw_label: str) -> RatingRecord:
        """테스트용: 라벨만으로 분류(등급 없음)."""
        row = ExtractedRatingRow(
            raw_label=raw_label,
            rating_cells=[],
            rating_status="none",
            rating=None,
            outlook=None,
            page=0,
            row_index=0,
            section=None,
            source="label_only",
        )
        return self.classify_row(row)
