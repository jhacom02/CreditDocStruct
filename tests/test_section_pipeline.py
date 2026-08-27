"""공용 섹션 카탈로그·그리드 해석 단위 테스트."""

from __future__ import annotations

from common.models import ExtractedTableGrid, VisualLine
from extract.rating_from_grid import (
    is_financial_noise_rating_row,
    rating_rows_from_grid,
)
from extract.regions import (
    PageRegion,
    PageRegions,
    gutter_from_side_by_side_headings,
)
from extract.section_catalog import (
    SECTION_FINANCIAL,
    SECTION_PRIMARY,
    SECTION_VALID,
    match_section_key,
    title_is_contaminated,
)


def test_rating_token_only_label_is_noise() -> None:
    assert is_financial_noise_rating_row(["A+ A A-", "", ""])
    assert not is_financial_noise_rating_row(["무보증사채", "AA", ""])


def test_match_section_key_aliases() -> None:
    assert match_section_key("평가 개요") == SECTION_PRIMARY
    assert match_section_key("평가등급") == SECTION_PRIMARY
    assert match_section_key("유효 등급") == SECTION_VALID
    assert match_section_key("주요 재무지표") == SECTION_FINANCIAL
    assert match_section_key("주요 재무 지표") == SECTION_FINANCIAL
    assert match_section_key("회사 개요") is None


def test_match_section_key_rejects_contaminated_valid_title() -> None:
    dirty = "유효등급 충당금/고정이하여신 112.3 203.7 247.5"
    assert title_is_contaminated(dirty) is True
    assert match_section_key(dirty) is None
    assert match_section_key("유효등급") == SECTION_VALID


def test_gutter_from_side_by_side_headings() -> None:
    lines = [
        VisualLine("유효등급", 40, 400, 100, 415),
        VisualLine("주요 재무지표", 320, 400, 420, 415),
        VisualLine("기업신용등급 AA+", 40, 430, 150, 445),
    ]
    gutter = gutter_from_side_by_side_headings(lines, page_width=600)
    assert gutter is not None
    assert 100 < gutter < 320


def test_preferred_region_resolve() -> None:
    regions = PageRegions(
        regions=(
            PageRegion("left", 0.0, 250.0),
            PageRegion("right", 250.0, 600.0),
        ),
        gutter_x=250.0,
    )
    heading = VisualLine(
        "유효등급 충당금/고정이하 1.0 2.0",
        40,
        400,
        500,
        415,
    )
    region = regions.resolve_heading_region(
        heading,
        anchor_x=50.0,
        preferred_region_id="left",
    )
    assert region.region_id == "left"


def test_rating_rows_filters_roa_peer_noise() -> None:
    assert is_financial_noise_rating_row(
        ["ROA(PEER)(%) 0.3 0.6 0.6 0.6 0.6", "N.A."]
    )
    grid = ExtractedTableGrid(
        section_key=SECTION_VALID,
        title_raw="유효등급",
        page=1,
        headers=["구분", "등급"],
        rows=[
            ["ROA(PEER)(%) 0.3 0.6 0.6 0.6 0.6", "N.A."],
            ["기업신용등급", "AA+/Stable"],
        ],
        source="visual_grid",
        region_id="left",
    )
    rows = rating_rows_from_grid(grid)
    assert len(rows) == 1
    assert rows[0].raw_label == "기업신용등급"
    assert rows[0].rating == "AA+"


def test_rating_rows_from_valid_grid() -> None:
    grid = ExtractedTableGrid(
        section_key=SECTION_VALID,
        title_raw="유효등급",
        page=1,
        headers=["구분", "등급"],
        rows=[
            ["기업신용등급", "AA+/Stable"],
            ["무보증사채", "AA+/Stable"],
        ],
        source="visual_grid",
        region_id="left",
    )
    rows = rating_rows_from_grid(grid)
    assert len(rows) == 2
    assert rows[0].section == "valid_ratings"
    assert rows[0].source == "valid_rating_section"
    assert rows[0].rating == "AA+"


def test_rating_rows_from_primary_grid() -> None:
    grid = ExtractedTableGrid(
        section_key=SECTION_PRIMARY,
        title_raw="평가 등급",
        page=1,
        headers=["구분", "종류", "현재등급", "직전등급", "비고"],
        rows=[
            ["기업신용등급", "본", "AAA/Stable", "", ""],
            ["무보증사채", "본", "AAA/Stable", "", ""],
        ],
        source="pdf_table",
    )
    rows = rating_rows_from_grid(grid)
    assert len(rows) >= 1
    assert rows[0].section == "primary_rating"
    assert rows[0].rating == "AAA"
