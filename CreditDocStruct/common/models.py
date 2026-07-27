"""ExtractedRatingRow / RatingRecord / VisualLine / 재무지표 데이터 모델."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RatingStatus = Literal["none", "single", "ambiguous"]
ClassificationStatus = Literal["matched", "undefined"]
MetricValueType = Literal["currency", "percent", "ratio", "text", "unknown"]


@dataclass
class VisualLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class ExtractedTableGrid:
    """공용 표 그리드 (등급·재무 섹션 공통)."""

    section_key: str
    title_raw: str
    page: int
    headers: list[str]
    rows: list[list[str]]
    region_id: str = "single"
    source: str = "pdf_table"
    basis: str | None = None
    unit_caption: str | None = None
    footnotes: list[str] = field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExtractedTableGrid:
        bbox = payload.get("bbox")
        return cls(
            section_key=str(payload.get("section_key") or ""),
            title_raw=str(payload.get("title_raw") or ""),
            page=int(payload.get("page") or 0),
            headers=list(payload.get("headers") or []),
            rows=[list(row) for row in (payload.get("rows") or [])],
            region_id=str(payload.get("region_id") or "single"),
            source=str(payload.get("source") or "pdf_table"),
            basis=payload.get("basis"),
            unit_caption=payload.get("unit_caption"),
            footnotes=list(payload.get("footnotes") or []),
            bbox=tuple(bbox) if bbox else None,
        )

    def to_fin_table(self) -> ExtractedFinTable:
        return ExtractedFinTable(
            page=self.page,
            title_raw=self.title_raw,
            headers=list(self.headers),
            rows=[list(row) for row in self.rows],
            source=self.source,
            basis=self.basis,
            unit_caption=self.unit_caption,
            footnotes=list(self.footnotes),
            bbox=self.bbox,
        )


@dataclass
class ExtractedFinTable:
    """주요 재무지표 표의 무손실 그리드."""

    page: int
    title_raw: str
    headers: list[str]
    rows: list[list[str]]
    source: str = "pdf_table"
    basis: str | None = None
    unit_caption: str | None = None
    footnotes: list[str] = field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExtractedFinTable:
        bbox = payload.get("bbox")
        return cls(
            page=int(payload.get("page") or 0),
            title_raw=str(payload.get("title_raw") or ""),
            headers=list(payload.get("headers") or []),
            rows=[list(row) for row in (payload.get("rows") or [])],
            source=str(payload.get("source") or "pdf_table"),
            basis=payload.get("basis"),
            unit_caption=payload.get("unit_caption"),
            footnotes=list(payload.get("footnotes") or []),
            bbox=tuple(bbox) if bbox else None,
        )


@dataclass
class FinancialFact:
    """표준 지표로 정규화된 재무지표 값."""

    metric_key: str | None
    raw_label: str
    normalized_label: str
    classification_status: ClassificationStatus
    period: str | None
    period_year: int | None
    period_month: int | None
    value: float | None
    value_raw: str | None
    unit: str | None
    value_type: MetricValueType
    basis: str | None
    page: int
    row_index: int
    col_index: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    header_cells: list[str] | None = None


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
