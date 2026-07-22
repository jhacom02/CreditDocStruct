"""페이지 좌/우 region 분할 (거터 기반).

유효등급(좌)과 주요 재무지표(우)가 같은 y에 있을 때 교차 clip을 막는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

from common.models import VisualLine
from common.text_utils import normalize_text
from extract.section_catalog import (
    SECTION_FINANCIAL,
    SECTION_VALID,
    compact_title,
    title_patterns_for,
)
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

    def region_by_id(self, region_id: str) -> PageRegion | None:
        for region in self.regions:
            if region.region_id == region_id:
                return region
        return None

    def region_for_x(self, x_mid: float) -> PageRegion:
        for region in self.regions:
            if region.x0 <= x_mid <= region.x1:
                return region
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
        anchor_x: float | None = None,
        preferred_region_id: str | None = None,
    ) -> pymupdf.Rect:
        region = self.resolve_heading_region(
            heading,
            anchor_x=anchor_x,
            preferred_region_id=preferred_region_id,
        )
        bottom = page.rect.height if end_y is None else end_y
        return pymupdf.Rect(
            max(0.0, region.x0 - pad),
            max(0.0, heading.y1),
            min(page.rect.width, region.x1 + pad),
            min(page.rect.height, bottom),
        )

    def resolve_heading_region(
        self,
        heading: VisualLine,
        *,
        anchor_x: float | None = None,
        preferred_region_id: str | None = None,
    ) -> PageRegion:
        """heading mid-x 대신 제목 앵커·선호 region으로 clip 기준을 고른다."""
        if preferred_region_id and self.gutter_x is not None:
            preferred = self.region_by_id(preferred_region_id)
            if preferred is not None:
                return preferred
        x = (
            anchor_x
            if anchor_x is not None
            else (heading.x0 + heading.x1) / 2
        )
        return self.region_for_x(x)


def _split_left_right(
    page_width: float,
    gutter_x: float,
    *,
    min_side_fraction: float,
) -> PageRegions | None:
    left_width = gutter_x
    right_width = page_width - gutter_x
    if (
        left_width < page_width * min_side_fraction
        or right_width < page_width * min_side_fraction
    ):
        return None
    return PageRegions(
        regions=(
            PageRegion("left", 0.0, gutter_x),
            PageRegion("right", gutter_x, page_width),
        ),
        gutter_x=gutter_x,
    )


def _line_mentions_section(text: str, section_key: str) -> bool:
    """제목 순도와 무관하게 섹션 키워드 포함 여부(거터 fallback용)."""
    normalized = normalize_text(text)
    if not normalized:
        return False
    for pattern in title_patterns_for(section_key):
        if re.search(pattern, normalized, re.IGNORECASE):
            return True
    return False


def gutter_from_side_by_side_headings(
    lines: list[VisualLine],
    page_width: float,
    *,
    y_tol: float = 48.0,
) -> float | None:
    """유효등급(좌)·주요재무지표(우)가 비슷한 y에 있으면 거터 x."""
    valid_lines = [
        line
        for line in lines
        if _line_mentions_section(line.text, SECTION_VALID)
    ]
    fin_lines = [
        line
        for line in lines
        if _line_mentions_section(line.text, SECTION_FINANCIAL)
    ]
    if not valid_lines or not fin_lines:
        return None

    best: tuple[float, float, float] | None = None
    # (y_gap, left_x1, right_x0) — y가 가깝고 좌우 분리된 쌍
    for valid in valid_lines:
        for fin in fin_lines:
            y_gap = abs(valid.y0 - fin.y0)
            if y_gap > y_tol:
                continue
            valid_mid = (valid.x0 + valid.x1) / 2
            fin_mid = (fin.x0 + fin.x1) / 2
            # 같은 visual line에 합쳐진 경우: 폭이 넓고 mid가 우측
            if valid is fin or (
                abs(valid.y0 - fin.y0) < 3
                and abs(valid.x0 - fin.x0) < 3
                and abs(valid.x1 - fin.x1) < 3
            ):
                # 페이지 중좌 거터 추정
                mid = page_width * 0.38
                if best is None or y_gap < best[0]:
                    best = (y_gap, mid, mid)
                continue
            if valid_mid >= fin_mid:
                continue
            gutter = (valid.x1 + fin.x0) / 2
            if not (page_width * 0.12 <= gutter <= page_width * 0.65):
                continue
            if best is None or y_gap < best[0]:
                best = (y_gap, gutter, gutter)

    if best is None:
        return None
    return best[1]


def title_anchor_x(
    page: pymupdf.Page,
    heading: VisualLine,
    section_key: str,
) -> float:
    """횡병합 제목 줄에서 섹션 제목 토큰의 좌측 x (없으면 heading.x0)."""
    clip = pymupdf.Rect(
        0,
        max(0.0, heading.y0 - 2),
        page.rect.width,
        min(page.rect.height, heading.y1 + 2),
    )
    words = page.get_text("words", clip=clip, sort=True)
    patterns = [
        re.compile(p, re.IGNORECASE) for p in title_patterns_for(section_key)
    ]
    # 단어들을 이어 붙여 패턴 위치를 찾고, 해당 span의 시작 x 사용
    if words:
        parts: list[tuple[str, float, float]] = []
        for word in words:
            text = normalize_text(str(word[4] or ""))
            if not text:
                continue
            parts.append((text, float(word[0]), float(word[2])))
        joined = ""
        spans: list[tuple[int, int, float]] = []  # start, end, x0
        for text, x0, _x1 in parts:
            start = len(joined)
            if joined:
                joined += " "
                start = len(joined)
            joined += text
            spans.append((start, len(joined), x0))
        for pattern in patterns:
            match = pattern.search(joined)
            if not match:
                continue
            for start, end, x0 in spans:
                if start <= match.start() < end or start < match.end() <= end:
                    return x0
                if match.start() <= start and end <= match.end():
                    return x0

    # compact alias가 heading 앞부분에 있으면 x0 사용
    compact = compact_title(heading.text)
    for pattern in title_patterns_for(section_key):
        if re.search(pattern, normalize_text(heading.text), re.IGNORECASE):
            return heading.x0
    del compact
    return heading.x0


def detect_page_regions(
    page: pymupdf.Page,
    *,
    min_gutter_gap: float = 22.0,
    min_side_fraction: float = 0.12,
    lines: list[VisualLine] | None = None,
) -> PageRegions:
    """word x 간격으로 세로 거터를 찾고, 실패 시 섹션 제목 쌍 fallback."""
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
    best_mid: float | None = None
    if len(centers) >= 4:
        best_gap = 0.0
        for left, right in zip(centers, centers[1:]):
            gap = right - left
            mid = (left + right) / 2
            # NICE 요지: 거터가 중~중좌에 오는 경우가 많음
            if gap < min_gutter_gap:
                continue
            if not (page_width * 0.15 <= mid <= page_width * 0.60):
                continue
            if gap > best_gap:
                best_gap = gap
                best_mid = mid

    if best_mid is not None:
        split = _split_left_right(
            page_width, best_mid, min_side_fraction=min_side_fraction
        )
        if split is not None:
            return split

    visual_lines = lines if lines is not None else extract_visual_lines(page)
    heading_gutter = gutter_from_side_by_side_headings(
        visual_lines, page_width
    )
    if heading_gutter is not None:
        split = _split_left_right(
            page_width,
            heading_gutter,
            min_side_fraction=min_side_fraction,
        )
        if split is not None:
            return split

    return PageRegions(
        regions=(PageRegion("single", 0.0, page_width),),
    )


def find_section_end_y(
    lines: list[VisualLine],
    heading: VisualLine,
    end_patterns: tuple[str, ...],
    *,
    region: PageRegion | None = None,
) -> float | None:
    """같은 region 안에서 heading 아래 첫 end 패턴 y0."""
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
