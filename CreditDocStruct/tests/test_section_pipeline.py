"""공용 섹션 카탈로그·그리드 해석 단위 테스트."""

from __future__ import annotations

from common.models import ExtractedTableGrid
from extract.rating_from_grid import rating_rows_from_grid
from extract.section_catalog import (
    SECTION_FINANCIAL,
    SECTION_PRIMARY,
    SECTION_VALID,
    match_section_key,
)


def test_match_section_key_aliases() -> None:
    assert match_section_key("평가 개요") == SECTION_PRIMARY
    assert match_section_key("평가등급") == SECTION_PRIMARY
    assert match_section_key("유효 등급") == SECTION_VALID
    assert match_section_key("주요 재무지표") == SECTION_FINANCIAL
    assert match_section_key("주요 재무 지표") == SECTION_FINANCIAL
    assert match_section_key("회사 개요") is None


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
