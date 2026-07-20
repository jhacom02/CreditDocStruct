"""word 좌표 → VisualLine 클러스터링."""

from __future__ import annotations

import re
from typing import Any, Iterable

import pymupdf

from common.models import VisualLine
from common.text_utils import normalize_text


def extract_visual_lines(
    page: pymupdf.Page,
    clip: pymupdf.Rect | None = None,
    y_tolerance: float = 3.5,
) -> list[VisualLine]:
    words = page.get_text("words", clip=clip, sort=True)

    if not words:
        return []

    word_items = []

    for word in words:
        x0, y0, x1, y1, text = word[:5]
        normalized = normalize_text(text)

        if not normalized:
            continue

        word_items.append(
            {
                "x0": float(x0),
                "y0": float(y0),
                "x1": float(x1),
                "y1": float(y1),
                "ymid": (float(y0) + float(y1)) / 2,
                "text": normalized,
            }
        )

    word_items.sort(key=lambda item: (item["ymid"], item["x0"]))

    clusters: list[list[dict[str, Any]]] = []

    for word in word_items:
        assigned = False

        for cluster in reversed(clusters[-5:]):
            cluster_y = sum(item["ymid"] for item in cluster) / len(cluster)

            if abs(word["ymid"] - cluster_y) <= y_tolerance:
                cluster.append(word)
                assigned = True
                break

        if not assigned:
            clusters.append([word])

    lines: list[VisualLine] = []

    for cluster in clusters:
        cluster.sort(key=lambda item: item["x0"])
        text = normalize_text(" ".join(item["text"] for item in cluster))
        lines.append(
            VisualLine(
                text=text,
                x0=min(item["x0"] for item in cluster),
                y0=min(item["y0"] for item in cluster),
                x1=max(item["x1"] for item in cluster),
                y1=max(item["y1"] for item in cluster),
            )
        )

    lines.sort(key=lambda line: (line.y0, line.x0))
    return lines


def find_heading_line(
    lines: list[VisualLine],
    patterns: Iterable[str],
) -> VisualLine | None:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

    for line in lines:
        for pattern in compiled:
            if pattern.search(normalize_text(line.text)):
                return line

    return None


def find_header_token_spans(
    page: pymupdf.Page,
    clip: pymupdf.Rect | None,
    token_names: tuple[str, ...],
) -> list[tuple[str, float, float, float]]:
    """헤더 토큰별 (name, x0, x1, ymid) 목록. 같은 헤더 줄에서만."""
    words = page.get_text("words", clip=clip, sort=True)
    if not words:
        return []

    targets = {
        re.sub(r"\s+", "", normalize_text(name)).lower(): name
        for name in token_names
    }
    items: list[dict[str, Any]] = []
    for word in words:
        x0, y0, x1, y1, text = word[:5]
        normalized = normalize_text(text)
        if not normalized:
            continue
        compact = re.sub(r"\s+", "", normalized).lower()
        matched_name: str | None = None
        for target, original in targets.items():
            if target in compact or compact in target:
                matched_name = original
                break
        if matched_name is None:
            continue
        items.append(
            {
                "name": matched_name,
                "x0": float(x0),
                "x1": float(x1),
                "ymid": (float(y0) + float(y1)) / 2,
            }
        )

    if not items:
        return []

    # 가장 위에 모인 헤더 줄 선택
    items.sort(key=lambda item: item["ymid"])
    base_y = items[0]["ymid"]
    same_row = [
        item for item in items if abs(item["ymid"] - base_y) <= 8.0
    ]
    same_row.sort(key=lambda item: item["x0"])

    # 이름당 첫 번째 span
    seen: set[str] = set()
    spans: list[tuple[str, float, float, float]] = []
    for item in same_row:
        key = re.sub(r"\s+", "", item["name"]).lower()
        if key in seen:
            continue
        seen.add(key)
        spans.append(
            (item["name"], item["x0"], item["x1"], item["ymid"])
        )
    return spans


def column_x_range_for_token(
    spans: list[tuple[str, float, float, float]],
    token_name: str,
    page_width: float,
) -> tuple[float, float] | None:
    """인접 헤더 midpoint로 열 x 범위 계산."""
    if not spans:
        return None

    target = re.sub(r"\s+", "", normalize_text(token_name)).lower()
    indexed = list(enumerate(spans))
    match_index: int | None = None
    for index, (name, _x0, _x1, _ymid) in indexed:
        compact = re.sub(r"\s+", "", normalize_text(name)).lower()
        if target in compact or compact in target:
            match_index = index
            break
    if match_index is None:
        return None

    _name, x0, x1, _ymid = spans[match_index]
    left = 0.0 if match_index == 0 else (spans[match_index - 1][2] + x0) / 2
    if match_index + 1 < len(spans):
        right = (x1 + spans[match_index + 1][1]) / 2
    else:
        right = min(page_width, x1 + max(40.0, (x1 - x0) * 1.5))
    return left, right


def text_in_x_range(
    page: pymupdf.Page,
    *,
    y0: float,
    y1: float,
    x0: float,
    x1: float,
) -> str:
    clip = pymupdf.Rect(x0, y0, x1, y1)
    words = page.get_text("words", clip=clip, sort=True)
    parts = [
        normalize_text(word[4])
        for word in words
        if normalize_text(word[4])
    ]
    return normalize_text(" ".join(parts))
