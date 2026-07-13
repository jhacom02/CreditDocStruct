from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RatingRecord:
    agency: str
    file_name: str
    page: int
    section: str
    source: str
    raw_label: str
    instrument_type: str
    evaluation_type: str | None
    current_rating: str
    current_outlook: str | None
    current_rating_display: str
    previous_rating: str | None
    previous_outlook: str | None
    previous_rating_display: str | None
    rating_action: str | None
    remark: str | None
    issue_name: str | None
    raw_text: str
    confidence: float
    classification_status: str = "matched"
    classification_score: float = 0.0
    classification_features: str | None = None
    classification_runner_up: str | None = None


@dataclass
class VisualLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
