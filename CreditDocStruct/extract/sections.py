"""페이지에서 표 제목 3종 → ExtractedTableGrid 공용 진입점."""

from __future__ import annotations

import pymupdf

from common.models import ExtractedTableGrid, VisualLine
from extract.grid import extract_table_grid
from extract.regions import (
    PageRegions,
    detect_page_regions,
    find_section_end_y,
)
from extract.section_catalog import (
    SECTION_CATALOG,
    SECTION_KEYS,
    end_patterns_for,
    match_section_key,
    title_patterns_for,
)
from extract.visual import extract_visual_lines, find_heading_line


def _heading_for_section(
    lines: list[VisualLine],
    section_key: str,
) -> VisualLine | None:
    # 카탈로그 패턴으로 먼저 탐색
    heading = find_heading_line(lines, title_patterns_for(section_key))
    if heading is not None:
        return heading
    # alias exact compact 매칭
    for line in lines:
        if match_section_key(line.text) == section_key:
            return line
    return None


def _near_texts(
    lines: list[VisualLine],
    heading: VisualLine,
    regions: PageRegions,
) -> list[str]:
    region = regions.region_for_x((heading.x0 + heading.x1) / 2)
    texts: list[str] = []
    for line in lines:
        if abs(line.y0 - heading.y0) > 45:
            continue
        mid = (line.x0 + line.x1) / 2
        if region.x0 <= mid <= region.x1:
            texts.append(line.text)
    return texts


def extract_section_tables(
    page: pymupdf.Page,
) -> dict[str, ExtractedTableGrid | None]:
    """페이지에서 3종 표 그리드를 추출한다. 없으면 해당 키는 None."""
    lines = extract_visual_lines(page)
    regions = detect_page_regions(page)
    results: dict[str, ExtractedTableGrid | None] = {
        key: None for key in SECTION_KEYS
    }

    # 모든 섹션 제목 y를 모아 end 경계로 사용
    headings: dict[str, VisualLine] = {}
    for key in SECTION_KEYS:
        heading = _heading_for_section(lines, key)
        if heading is not None:
            headings[key] = heading

    for key, heading in headings.items():
        region = regions.region_for_x((heading.x0 + heading.x1) / 2)
        end_y = find_section_end_y(
            lines,
            heading,
            end_patterns_for(key),
            region=region,
        )
        # 같은 region 안의 다른 섹션 제목도 하단 경계
        for other_key, other in headings.items():
            if other_key == key:
                continue
            other_region = regions.region_for_x((other.x0 + other.x1) / 2)
            if other_region.region_id != region.region_id:
                continue
            if other.y0 > heading.y1 + 5:
                end_y = (
                    other.y0
                    if end_y is None
                    else min(end_y, other.y0)
                )

        clip = regions.clip_for_heading(
            heading,
            page=page,
            end_y=end_y if end_y is not None else page.rect.height,
        )
        grid = extract_table_grid(
            page,
            clip,
            section_key=key,
            title_raw=heading.text,
            region_id=region.region_id,
            near_texts=_near_texts(lines, heading, regions),
        )
        results[key] = grid

    return results


def extract_section_tables_from_document(
    document: pymupdf.Document,
    *,
    max_pages: int,
) -> dict[str, list[ExtractedTableGrid]]:
    """문서 페이지들을 합쳐 section_key → grids 목록."""
    merged: dict[str, list[ExtractedTableGrid]] = {
        key: [] for key in SECTION_KEYS
    }
    page_count = min(max_pages, len(document))
    for index in range(page_count):
        page_result = extract_section_tables(document[index])
        for key, grid in page_result.items():
            if grid is not None:
                merged[key].append(grid)
    return merged
