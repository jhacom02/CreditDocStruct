"""ExtractedRatingRow / RatingRecord / VisualLine 데이터 모델.

추출 단계(row_parser)가 ExtractedRatingRow를 만들고,
분류 단계(classifier)가 RatingRecord로 변환한다.

Plan: creditratefinder_restructure_43c68190 섹션 E 참고.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RatingStatus = Literal["none", "single", "ambiguous"]
ClassificationStatus = Literal["matched", "undefined"]


@dataclass
class VisualLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class ExtractedRatingRow:
    """추출 단계 결과. rating 셀 개수·모호성 판정까지 포함."""

    raw_label: str
    rating_cells: list[str]
    rating_status: RatingStatus
    rating: str | None
    outlook: str | None
    page: int
    row_index: int
    section: str | None = None
    source: str = "unknown"
    cells: list[str] = field(default_factory=list)
    evaluation_type: str | None = None
    issue_name: str | None = None
    remark: str | None = None
    label_text: str | None = None
    raw_outlook: str | None = None


@dataclass
class Suggestion:
    instrument_key: str
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RatingRecord:
    """분류 단계 결과. rating 필드는 ExtractedRatingRow에서 그대로 이전."""

    raw_label: str
    normalized_label: str
    instrument_key: str | None
    classification_status: ClassificationStatus
    rating: str | None
    outlook: str | None
    rating_status: RatingStatus
    page: int
    row_index: int
    section: str | None = None
    source: str = "unknown"
    suggestions: list[Suggestion] = field(default_factory=list)
    evaluation_type: str | None = None
    issue_name: str | None = None
    remark: str | None = None
    label_text: str | None = None
    raw_outlook: str | None = None
    confirmed_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload
