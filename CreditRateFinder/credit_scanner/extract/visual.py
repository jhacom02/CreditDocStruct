from __future__ import annotations

import re
from typing import Any, Iterable

import pymupdf

from credit_scanner.models import VisualLine
from credit_scanner.text_utils import normalize_text


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
