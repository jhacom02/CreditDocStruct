"""페이지 좌/우 region 분할 (거터 기반).

유효등급(좌)과 주요 재무지표(우)가 같은 y에 있을 때 교차 clip을 막는다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from common.models import VisualLine
from extract.visual import extract_visual_lines


@dataclass(frozen=True)
class PageRegion:
    region_id: str
    x0: float
    x1: float


@dataclass(frozen=True)
class PageRegions:
    regions: tuple[PageRegion, ...]
    gutter_x: float | None = None

    def region_for_x(self, x_mid: float) -> PageRegion:
        for region in self.regions:
            if region.x0 <= x_mid <= region.x1:
                return region
        # 가장 가까운 region
        return min(
            self.regions,
            key=lambda item: min(
                abs(x_mid - item.x0), abs(x_mid - item.x1)
            ),
        )

    def clip_for_heading(
        self,
        heading: VisualLine,
        *,
        page: pymupdf.Page,
        end_y: float | None = None,
        pad: float = 4.0,
    ) -> pymupdf.Rect:
        region = self.region_for_x((heading.x0 + heading.x1) / 2)
        bottom = page.rect.height if end_y is None else end_y
        return pymupdf.Rect(
            max(0.0, region.x0 - pad),
            max(0.0, heading.y1),
            min(page.rect.width, region.x1 + pad),
            min(page.rect.height, bottom),
        )


def detect_page_regions(
    page: pymupdf.Page,
    *,
    min_gutter_gap: float = 28.0,
    min_side_fraction: float = 0.12,
) -> PageRegions:
    """word x 간격으로 세로 거터를 찾아 left/right 또는 single region을 만든다."""
    words = page.get_text("words", sort=True)
    page_width = float(page.rect.width)
    if not words or page_width <= 0:
        return PageRegions(
            regions=(PageRegion("single", 0.0, page_width),),
        )

    centers = sorted(
        {
            round((float(word[0]) + float(word[2])) / 2, 1)
            for word in words
            if word[4] and str(word[4]).strip()
        }
    )
    if len(centers) < 4:
        return PageRegions(
            regions=(PageRegion("single", 0.0, page_width),),
        )

    best_gap = 0.0
    best_mid: float | None = None
    for left, right in zip(centers, centers[1:]):
        gap = right - left
        mid = (left + right) / 2
        # 페이지 중앙 대역의 큰 간격만 거터 후보
        if gap < min_gutter_gap:
            continue
        if not (page_width * 0.18 <= mid <= page_width * 0.55):
            continue
        if gap > best_gap:
            best_gap = gap
            best_mid = mid

    if best_mid is None:
        return PageRegions(
            regions=(PageRegion("single", 0.0, page_width),),
        )

    left_width = best_mid
    right_width = page_width - best_mid
    if (
        left_width < page_width * min_side_fraction
        or right_width < page_width * min_side_fraction
    ):
        return PageRegions(
            regions=(PageRegion("single", 0.0, page_width),),
        )

    return PageRegions(
        regions=(
            PageRegion("left", 0.0, best_mid),
            PageRegion("right", best_mid, page_width),
        ),
        gutter_x=best_mid,
    )


def find_section_end_y(
    lines: list[VisualLine],
    heading: VisualLine,
    end_patterns: tuple[str, ...],
    *,
    region: PageRegion | None = None,
) -> float | None:
    """같은 region 안에서 heading 아래 첫 end 패턴 y0."""
    import re

    from common.text_utils import normalize_text

    compiled = [re.compile(p, re.IGNORECASE) for p in end_patterns]
    for line in lines:
        if line.y0 <= heading.y1 + 5:
            continue
        if region is not None:
            mid = (line.x0 + line.x1) / 2
            if not (region.x0 <= mid <= region.x1):
                continue
        text = normalize_text(line.text)
        if any(pattern.search(text) for pattern in compiled):
            return line.y0
    return None
