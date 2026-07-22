"""ExtractedTableGrid → ExtractedRatingRow (등급 L3 입력)."""

from __future__ import annotations

from common.models import ExtractedRatingRow, ExtractedTableGrid
from extract.row_parser import parse_rating_row_values
from extract.section_catalog import SECTION_PRIMARY, SECTION_VALID


def rating_rows_from_grid(
    grid: ExtractedTableGrid,
) -> list[ExtractedRatingRow]:
    """공용 그리드를 기존 등급 파서 입력으로 변환한다."""
    if grid.section_key == SECTION_PRIMARY:
        section = "primary_rating"
        source = (
            "pdf_table" if grid.source == "pdf_table" else "visual_layout"
        )
    elif grid.section_key == SECTION_VALID:
        section = "valid_ratings"
        source = "valid_rating_section"
    else:
        return []

    records: list[ExtractedRatingRow] = []
    header_cells = list(grid.headers) if grid.headers else None
    row_index = 0
    for values in grid.rows:
        if not any(str(cell).strip() for cell in values):
            continue
        # valid 2열: 등급 열을 current_rating_cell로도 전달
        current_cell = None
        if grid.section_key == SECTION_VALID and len(values) >= 2:
            current_cell = values[1] or None

        record = parse_rating_row_values(
            values=list(values),
            page_number=grid.page,
            row_index=row_index,
            section=section,
            source=source,
            header_cells=header_cells,
            current_rating_cell=current_cell,
        )
        if record is None:
            continue
        if (
            grid.section_key == SECTION_VALID
            and record.rating_status == "none"
            and not record.rating
        ):
            continue
        records.append(record)
        row_index += 1
    return records


def rating_rows_from_section_tables(
    section_tables: dict[str, ExtractedTableGrid | None] | dict[str, list],
) -> list[ExtractedRatingRow]:
    """section 결과에서 primary+valid 등급 행만 모은다."""
    rows: list[ExtractedRatingRow] = []
    for key in (SECTION_PRIMARY, SECTION_VALID):
        value = section_tables.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            for grid in value:
                rows.extend(rating_rows_from_grid(grid))
        else:
            rows.extend(rating_rows_from_grid(value))
    return rows
