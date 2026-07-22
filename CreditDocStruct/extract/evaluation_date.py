"""PDF에서 평가일(발행일/등급확정일) 추출."""

from __future__ import annotations

import re
from pathlib import Path

from common.text_utils import normalize_text

_LABEL_DATE_RE = re.compile(
    r"(?:등급\s*확정일|발행일|평가일)\s*[:：]?\s*"
    r"(?P<y>20\d{2})\s*[.\-/년]\s*(?P<m>\d{1,2})\s*[.\-/월]?\s*(?P<d>\d{1,2})",
    re.IGNORECASE,
)

_ANY_DATE_RE = re.compile(
    r"(?P<y>20\d{2})\s*[.\-/]\s*(?P<m>\d{1,2})\s*[.\-/]\s*(?P<d>\d{1,2})"
)

_FILENAME_DATE_RE = re.compile(
    r"(?:^|[_\-])(?:rs|RS)?(?P<y>20\d{2})(?P<m>\d{2})(?P<d>\d{2})(?:[_\-]|$)",
)


def _format_date(year: int, month: int, day: int) -> str | None:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}.{month:02d}.{day:02d}"


def evaluation_date_from_text(text: str | None) -> str | None:
    """본문에서 평가일을 YYYY.MM.DD로 추출."""
    normalized = normalize_text(text)
    if not normalized:
        return None
    match = _LABEL_DATE_RE.search(normalized)
    if match:
        return _format_date(
            int(match.group("y")),
            int(match.group("m")),
            int(match.group("d")),
        )
    compact = re.sub(r"\s+", "", normalized)
    for label in ("등급확정일", "발행일", "평가일"):
        idx = compact.find(label)
        if idx < 0:
            continue
        window = compact[idx : idx + 40]
        any_match = _ANY_DATE_RE.search(window)
        if any_match:
            return _format_date(
                int(any_match.group("y")),
                int(any_match.group("m")),
                int(any_match.group("d")),
            )
    return None


def evaluation_date_from_filename(file_name: str | Path) -> str | None:
    """파일명 rsYYYYMMDD 패턴 fallback."""
    stem = Path(file_name).stem
    match = _FILENAME_DATE_RE.search(stem)
    if not match:
        loose = re.search(r"(?:rs|RS)(?P<y>20\d{2})(?P<m>\d{2})(?P<d>\d{2})", stem)
        if not loose:
            return None
        match = loose
    return _format_date(
        int(match.group("y")),
        int(match.group("m")),
        int(match.group("d")),
    )


def extract_evaluation_date(
    page_text: str | None,
    file_name: str | Path,
) -> str | None:
    return evaluation_date_from_text(page_text) or evaluation_date_from_filename(
        file_name
    )
