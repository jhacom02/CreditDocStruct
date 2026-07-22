"""페이지에서 표 제목 3종 → ExtractedTableGrid 공용 진입점."""

from __future__ import annotations

import re

import pymupdf

from common.models import ExtractedTableGrid, VisualLine
from common.text_utils import normalize_text
from extract.grid import extract_table_grid
from extract.regions import (
    PageRegion,
    PageRegions,
    detect_page_regions,
    find_section_end_y,
    title_anchor_x,
)
from extract.section_catalog import (
    PREFERRED_REGION_BY_SECTION,
    SECTION_CATALOG,
    SECTION_FINANCIAL,
    SECTION_KEYS,
    SECTION_VALID,
    end_patterns_for,
    match_section_key,
    title_patterns_for,
)
from extract.visual import extract_visual_lines


def _pattern_hits(text: str, patterns: tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    return any(
        re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns
    )


def _heading_candidates(
    lines: list[VisualLine],
    section_key: str,
) -> list[VisualLine]:
    """순수 제목 우선. 없으면 패턴만 맞는 오염 줄(위치용)."""
    patterns = title_patterns_for(section_key)
    pure: list[VisualLine] = []
    soft: list[VisualLine] = []
    seen: set[tuple[float, float, str]] = set()
    for line in lines:
        key = (round(line.y0, 1), round(line.x0, 1), line.text[:40])
        if key in seen:
            continue
        if match_section_key(line.text) == section_key:
            seen.add(key)
            pure.append(line)
        elif _pattern_hits(line.text, patterns):
            seen.add(key)
            soft.append(line)
    return pure or soft


def _pick_heading(
    candidates: list[VisualLine],
    section_key: str,
    regions: PageRegions,
) -> VisualLine | None:
    if not candidates:
        return None
    preferred_id = PREFERRED_REGION_BY_SECTION.get(section_key)

    def score(line: VisualLine) -> tuple:
        # 순수 제목·짧은 줄·선호 region 우선
        pure = 0 if match_section_key(line.text) == section_key else 1
        length = len(re.sub(r"\s+", "", normalize_text(line.text)))
        mid = (line.x0 + line.x1) / 2
        region = regions.region_for_x(mid)
        region_bonus = 0
        if preferred_id and regions.gutter_x is not None:
            if region.region_id == preferred_id:
                region_bonus = -1000
            else:
                region_bonus = 500
        side_score = mid if preferred_id == "right" else -mid
        return (pure, region_bonus, length, side_score, line.y0)

    return min(candidates, key=score)


def _heading_for_section(
    lines: list[VisualLine],
    section_key: str,
    regions: PageRegions,
) -> VisualLine | None:
    candidates = _heading_candidates(lines, section_key)
    return _pick_heading(candidates, section_key, regions)


def _near_texts(
    lines: list[VisualLine],
    heading: VisualLine,
    region: PageRegion,
) -> list[str]:
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
    regions = detect_page_regions(page, lines=lines)
    results: dict[str, ExtractedTableGrid | None] = {
        key: None for key in SECTION_KEYS
    }

    headings: dict[str, VisualLine] = {}
    for key in SECTION_KEYS:
        heading = _heading_for_section(lines, key, regions)
        if heading is not None:
            headings[key] = heading

    for key, heading in headings.items():
        preferred_id = PREFERRED_REGION_BY_SECTION.get(key)
        anchor = title_anchor_x(page, heading, key)
        region = regions.resolve_heading_region(
            heading,
            anchor_x=anchor,
            preferred_region_id=preferred_id,
        )
        end_y = find_section_end_y(
            lines,
            heading,
            end_patterns_for(key),
            region=region,
        )
        for other_key, other in headings.items():
            if other_key == key:
                continue
            other_preferred = PREFERRED_REGION_BY_SECTION.get(other_key)
            other_anchor = title_anchor_x(page, other, other_key)
            other_region = regions.resolve_heading_region(
                other,
                anchor_x=other_anchor,
                preferred_region_id=other_preferred,
            )
            if other.y0 <= heading.y1 + 5:
                continue
            # 같은 region: 기존처럼 하단 경계
            # 좌우 배치: 재무(우) clip이 아래쪽 유효등급 밴드와 섞이지 않게
            # valid 제목 y도 financial end로 사용
            same_region = other_region.region_id == region.region_id
            cross_fin_valid = (
                key == SECTION_FINANCIAL
                and other_key == SECTION_VALID
                and regions.gutter_x is not None
            )
            if same_region or cross_fin_valid:
                end_y = (
                    other.y0
                    if end_y is None
                    else min(end_y, other.y0)
                )

        clip = regions.clip_for_heading(
            heading,
            page=page,
            end_y=end_y if end_y is not None else page.rect.height,
            anchor_x=anchor,
            preferred_region_id=preferred_id,
        )
        title_raw = (
            heading.text
            if match_section_key(heading.text) == key
            else SECTION_CATALOG[key].title_aliases[0]
        )

        grid = extract_table_grid(
            page,
            clip,
            section_key=key,
            title_raw=title_raw,
            region_id=region.region_id,
            near_texts=_near_texts(lines, heading, region),
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
