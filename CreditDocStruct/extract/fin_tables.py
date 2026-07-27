"""주요 재무지표 표 → ExtractedFinTable (무손실 그리드)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import pymupdf

from common.models import ExtractedFinTable
from common.text_utils import normalize_text
from extract.regions import (
    detect_page_regions,
    find_section_end_y,
)
from extract.visual import extract_visual_lines, find_heading_line

FINANCIAL_TITLE_PATTERNS: tuple[str, ...] = (
    r"주요\s*재무\s*지표",
)

FINANCIAL_END_PATTERNS: tuple[str, ...] = (
    r"평정\s*논거",
    r"주\s*\)",
    r"자료\s*[:：]",
    r"등급\s*정의",
    r"평가\s*담당자",
    r"주요\s*평가\s*요소",
    r"업체\s*개요",
    r"회사\s*개요",
)

_NARRATIVE_LABEL_RE = re.compile(
    r"^(?:평정\s*논거|\d+\.\s|[\uf06c\u2022•●◦▪-]\s*)",
)
_APPLIED_STATEMENTS_RE = re.compile(r"적용\s*재무\s*제표")

_PERIOD_RE = re.compile(
    r"(?P<year>20\d{2})"
    r"(?:\s*[.\-/]?\s*\(?(?P<month>1[0-2]|0[1-9]|[1-9])\)?)?",
)
_YEAR_ONLY_RE = re.compile(r"^(20\d{2})$")
_BASIS_RE = re.compile(
    r"(K-?IFRS|IFRS|별도|연결|개별|은행계정|공기업|준정부)",
    re.IGNORECASE,
)
_UNIT_CAPTION_RE = re.compile(
    r"단위\s*[:：]?\s*([^\n)]+)",
    re.IGNORECASE,
)
_FOOTNOTE_MARK_RE = re.compile(r"(주\s*\d+\s*\)|\(\s*\d+\s*\)|\*\d*)\s*$")
_EMPTY_VALUE_RE = re.compile(
    r"^(?:n\.?\s*a\.?|-|—|–|해당없음|없음)?$",
    re.IGNORECASE,
)
_LABEL_TRAILING_NUM_RE = re.compile(
    r"^(?P<label>.+?)\s+(?P<num>[\d,]+(?:\.\d+)?)\s*$"
)
_NUMERIC_TOKEN_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")
_CONCAT_NUMBERS_ONLY_RE = re.compile(
    r"^[\s,.\-△▲()]*"
    r"(?:-?[\d,]+(?:\.\d+)?)"
    r"(?:\s+-?[\d,]+(?:\.\d+)?)+"
    r"[\s,.\-△▲()]*$"
)


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


def _digits_only(text: str | None) -> str:
    return re.sub(r"[^\d]", "", text or "")


def take_first_concatenated_number(text: str | None) -> str | None:
    """공백으로 붙은 복수 수치 셀이면 첫 수치만 남긴다."""
    raw = normalize_text(text)
    if not raw or not _CONCAT_NUMBERS_ONLY_RE.match(raw):
        return None
    match = _NUMERIC_TOKEN_RE.search(raw)
    return match.group(0) if match else None


def repair_financial_row_label(row: list[Any]) -> list[Any]:
    """라벨 셀에 붙은 trailing 수치를 분리하고 첫 기간열을 복구한다."""
    if not row:
        return row
    label = normalize_text(str(row[0] or ""))
    if not label:
        return list(row)

    match = _LABEL_TRAILING_NUM_RE.match(label)
    if not match:
        return list(row)

    clean_label = normalize_text(match.group("label"))
    trailing_num = match.group("num")
    trailing_digits = _digits_only(trailing_num)
    if not clean_label or not trailing_digits:
        return list(row)

    new_row = list(row)
    new_row[0] = clean_label
    if len(new_row) <= 1:
        return new_row

    first_val = str(new_row[1] or "").strip()
    first_digits = _digits_only(first_val)
    if not first_val:
        new_row[1] = trailing_num
    elif len(first_digits) > len(trailing_digits) + 3:
        new_row[1] = trailing_num
    elif first_digits == trailing_digits:
        new_row[1] = trailing_num

    return new_row


def repair_financial_value_cells(row: list[Any]) -> list[Any]:
    """값 열의 복수 수치 concat을 첫 수치로 정리한다."""
    if not row:
        return row
    new_row = list(row)
    for index in range(1, len(new_row)):
        first = take_first_concatenated_number(new_row[index])
        if first is not None:
            new_row[index] = first
    return new_row


def align_sparse_period_columns(
    headers: list[Any],
    rows: list[list[Any]],
) -> tuple[list[str], list[list[str]]]:
    """빈 헤더 열에 수치가 있고 기간 헤더 아래가 비어 있으면 값을 기간 열로 옮긴 뒤 라벨+기간 열만 남긴다."""
    if not headers:
        return [], [list(map(lambda c: normalize_text(str(c or "")), row)) for row in rows]

    width = max(
        [len(headers)] + [len(row) for row in rows],
        default=0,
    )
    norm_headers = [
        normalize_text(str(headers[i] if i < len(headers) else "") or "")
        for i in range(width)
    ]
    work_rows: list[list[str]] = []
    for row in rows:
        work_rows.append(
            [
                normalize_text(str(row[i] if i < len(row) else "") or "")
                for i in range(width)
            ]
        )

    period_idxs = [
        index
        for index in range(1, width)
        if parse_period_header(norm_headers[index])[0] is not None
    ]
    if not period_idxs:
        return norm_headers[: len(headers)] or norm_headers, work_rows

    for row in work_rows:
        for period_index in period_idxs:
            current = row[period_index]
            if current.strip():
                continue
            prev_index = period_index - 1
            if prev_index < 1:
                continue
            if norm_headers[prev_index].strip():
                continue
            prev_val = row[prev_index]
            if not prev_val.strip():
                continue
            if parse_numeric_cell(prev_val)[0] is None:
                first = take_first_concatenated_number(prev_val)
                if first is None:
                    continue
                prev_val = first
            row[period_index] = prev_val
            row[prev_index] = ""

    keep = [0] + period_idxs
    out_headers = [norm_headers[i] for i in keep]
    if not out_headers[0].strip():
        out_headers[0] = "구분"
    out_rows = [[row[i] for i in keep] for row in work_rows]
    return out_headers, out_rows


def repair_financial_matrix(
    headers: list[Any],
    rows: list[list[Any]],
) -> tuple[list[str], list[list[str]]]:
    """라벨 trailing, 값 concat, 빈 기간열 정렬을 한 번에 적용."""
    repaired = [
        repair_financial_value_cells(repair_financial_row_label(list(row)))
        for row in rows
    ]
    return align_sparse_period_columns(headers, repaired)


def repair_financial_data_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """모든 데이터 행에 라벨 trailing, 값 concat 정리를 적용."""
    return [
        repair_financial_value_cells(repair_financial_row_label(list(row)))
        for row in rows
    ]


def filter_financial_data_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """적용재무제표 이후, 서술/각주/불릿 행 제거."""
    filtered: list[list[Any]] = []
    for row in rows:
        if not row:
            continue
        label = normalize_text(str(row[0] or ""))
        if not label.strip():
            if not any(str(cell or "").strip() for cell in row[1:]):
                continue
            filtered.append(row)
            continue
        if _APPLIED_STATEMENTS_RE.search(label):
            filtered.append(row)
            break
        if _NARRATIVE_LABEL_RE.search(label):
            break
        if "평정논거" in _compact(label) or _compact(label).startswith("평정논거"):
            break
        has_number = False
        for cell in row[1:]:
            value, _ = parse_numeric_cell(cell if cell is not None else None)
            if value is not None:
                has_number = True
                break
        if not has_number and len(label) > 20:
            continue
        filtered.append(row)
    return repair_financial_data_rows(filtered)


def parse_period_header(text: str | None) -> tuple[str | None, int | None, int | None]:
    """기간 헤더 → (canonical 'YYYY.MM', year, month). 연도만 있으면 연말(`.12`)로 정규화."""
    normalized = normalize_text(text)
    if not normalized:
        return None, None, None
    compact = re.sub(r"\s+", "", normalized)
    year_only = _YEAR_ONLY_RE.fullmatch(compact)
    if year_only:
        year = int(year_only.group(1))
        return f"{year:04d}.12", year, 12
    match = _PERIOD_RE.fullmatch(compact) or _PERIOD_RE.search(normalized)
    if not match:
        return None, None, None
    year = int(match.group("year"))
    month_raw = match.group("month")
    month = int(month_raw) if month_raw else 12
    return f"{year:04d}.{month:02d}", year, month


def parse_numeric_cell(text: str | None) -> tuple[float | None, str | None]:
    """셀 텍스트 → (float|None, raw). n.a./- 는 None."""
    raw = normalize_text(text)
    if not raw or _EMPTY_VALUE_RE.match(_compact(raw)):
        return None, raw or None

    cleaned = raw.replace(",", "").replace(" ", "")
    cleaned = cleaned.replace("△", "-").replace("▲", "")
    if re.fullmatch(r"\(\s*-?[\d.]+\s*\)", cleaned):
        cleaned = "-" + cleaned.strip("()")

    try:
        value = float(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None, raw
    return value, raw


def strip_footnote_marker(label: str) -> tuple[str, str | None]:
    text = normalize_text(label)
    match = _FOOTNOTE_MARK_RE.search(text)
    if not match:
        return text, None
    mark = match.group(1)
    cleaned = normalize_text(text[: match.start()])
    return cleaned or text, mark


def infer_unit_from_label(label: str) -> str | None:
    compact = _compact(label)
    if "(%)" in label or "％" in label or compact.endswith("%"):
        return "percent"
    if "(배)" in label or "배수" in compact:
        return "ratio"
    if "십억원" in compact:
        return "십억원"
    if "억원" in compact:
        return "억원"
    if "백만원" in compact:
        return "백만원"
    return None


def _detect_basis(texts: list[str]) -> str | None:
    joined = " ".join(normalize_text(t) for t in texts if t)
    if not joined:
        return None
    if "연결" in joined:
        return "연결"
    if "별도" in joined or "개별" in joined:
        return "별도"
    if "은행계정" in joined:
        return "은행계정"
    match = _BASIS_RE.search(joined)
    return match.group(0) if match else None


def _detect_unit_caption(texts: list[str]) -> str | None:
    for text in texts:
        match = _UNIT_CAPTION_RE.search(normalize_text(text))
        if match:
            return normalize_text(match.group(0))
    return None


def _clean_matrix(matrix: list[list[Any]]) -> list[list[str]]:
    return [
        [normalize_text(cell) if cell is not None else "" for cell in row]
        for row in matrix
    ]


def _header_row_index(matrix: list[list[str]]) -> int | None:
    best_index: int | None = None
    best_count = 0
    for index, row in enumerate(matrix[:6]):
        period_count = sum(
            1 for cell in row if parse_period_header(cell)[0] is not None
        )
        if period_count >= 2 and period_count > best_count:
            best_count = period_count
            best_index = index
    return best_index


def _table_overlaps_clip(
    table: object,
    clip: pymupdf.Rect,
) -> bool:
    bbox = getattr(table, "bbox", None)
    if not bbox:
        return True
    try:
        rect = pymupdf.Rect(bbox)
    except Exception:
        return True
    return rect.intersects(clip)


def _extract_footnotes(
    lines: list[Any],
    table_bottom: float,
    *,
    max_y_gap: float = 80.0,
) -> list[str]:
    notes: list[str] = []
    for line in lines:
        if line.y0 < table_bottom - 2:
            continue
        if line.y0 > table_bottom + max_y_gap:
            break
        text = normalize_text(line.text)
        compact = _compact(text)
        if compact.startswith("주") or compact.startswith("자료"):
            notes.append(text)
        elif notes and (text.startswith("1.") or text.startswith("2.")):
            notes.append(text)
    return notes


def _from_pymupdf_table(
    table: object,
    *,
    page_number: int,
    title_raw: str,
    unit_caption: str | None,
    basis_hint: str | None,
) -> ExtractedFinTable | None:
    try:
        matrix = table.extract()
    except Exception:
        return None
    if not matrix:
        return None

    cleaned = _clean_matrix(matrix)
    header_index = _header_row_index(cleaned)
    if header_index is None:
        return None

    headers = list(cleaned[header_index])
    data_rows = [
        list(row)
        for row in cleaned[header_index + 1 :]
        if any(cell.strip() for cell in row)
    ]
    data_rows = filter_financial_data_rows(data_rows)
    if not data_rows:
        return None

    headers, data_rows = repair_financial_matrix(headers, data_rows)
    if not data_rows:
        return None

    basis = basis_hint
    if header_index > 0:
        basis = basis or _detect_basis(
            [" ".join(row) for row in cleaned[:header_index]]
        )
    if basis is None:
        basis = _detect_basis([" ".join(headers)])

    bbox = None
    raw_bbox = getattr(table, "bbox", None)
    if raw_bbox:
        try:
            rect = pymupdf.Rect(raw_bbox)
            bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
        except Exception:
            bbox = None

    return ExtractedFinTable(
        page=page_number,
        title_raw=title_raw,
        headers=headers,
        rows=data_rows,
        source="pdf_table",
        basis=basis,
        unit_caption=unit_caption,
        footnotes=[],
        bbox=bbox,
    )


def _visual_fin_grid(
    page: pymupdf.Page,
    clip: pymupdf.Rect,
    *,
    page_number: int,
    title_raw: str,
    unit_caption: str | None,
    basis: str | None,
) -> ExtractedFinTable | None:
    """find_tables 실패 시: 기간 토큰 x로 열을 나누고 y 밴드로 행을 구성."""
    words = page.get_text("words", clip=clip, sort=True)
    if not words:
        return None

    period_words: list[dict[str, Any]] = []
    for word in words:
        x0, y0, x1, y1, text = word[:5]
        period, year, month = parse_period_header(text)
        if period is None:
            continue
        period_words.append(
            {
                "text": period,
                "x0": float(x0),
                "x1": float(x1),
                "ymid": (float(y0) + float(y1)) / 2,
                "year": year,
                "month": month,
            }
        )
    if len(period_words) < 2:
        return None

    period_words.sort(key=lambda item: item["ymid"])
    header_y = period_words[0]["ymid"]
    header_items = [
        item for item in period_words if abs(item["ymid"] - header_y) <= 10.0
    ]
    header_items.sort(key=lambda item: item["x0"])
    seen: set[str] = set()
    unique_headers: list[dict[str, Any]] = []
    for item in header_items:
        if item["text"] in seen:
            continue
        seen.add(item["text"])
        unique_headers.append(item)
    if len(unique_headers) < 2:
        return None

    col_bounds: list[tuple[float, float]] = []
    first_x0 = unique_headers[0]["x0"]
    label_right = max(clip.x0 + 10.0, first_x0 - 4.0)
    col_bounds.append((clip.x0, label_right))
    for index, item in enumerate(unique_headers):
        left = item["x0"] - 2
        if index + 1 < len(unique_headers):
            right = (item["x1"] + unique_headers[index + 1]["x0"]) / 2
        else:
            right = clip.x1
        col_bounds.append((left, right))

    headers = ["구분"] + [item["text"] for item in unique_headers]

    data_words = [
        {
            "x0": float(w[0]),
            "y0": float(w[1]),
            "x1": float(w[2]),
            "y1": float(w[3]),
            "ymid": (float(w[1]) + float(w[3])) / 2,
            "text": normalize_text(w[4]),
        }
        for w in words
        if normalize_text(w[4]) and (float(w[1]) + float(w[3])) / 2 > header_y + 8
    ]
    if not data_words:
        return None

    data_words.sort(key=lambda item: (item["ymid"], item["x0"]))
    rows_cluster: list[list[dict[str, Any]]] = []
    for word in data_words:
        if rows_cluster:
            prev_y = sum(item["ymid"] for item in rows_cluster[-1]) / len(
                rows_cluster[-1]
            )
            if abs(word["ymid"] - prev_y) <= 4.0:
                rows_cluster[-1].append(word)
                continue
        rows_cluster.append([word])

    grid_rows: list[list[str]] = []
    for cluster in rows_cluster:
        y0 = min(item["y0"] for item in cluster) - 1
        y1 = max(item["y1"] for item in cluster) + 1
        row_values: list[str] = []
        for x0, x1 in col_bounds:
            parts = [
                item["text"]
                for item in cluster
                if item["x0"] < x1 and item["x1"] > x0
            ]
            row_values.append(normalize_text(" ".join(parts)))
        if any(row_values):
            label = _compact(row_values[0])
            if label.startswith("주") or label.startswith("자료"):
                continue
            grid_rows.append(row_values)

    if not grid_rows:
        return None

    grid_rows = filter_financial_data_rows(grid_rows)
    if not grid_rows:
        return None

    headers, grid_rows = repair_financial_matrix(headers, grid_rows)
    if not grid_rows:
        return None

    return ExtractedFinTable(
        page=page_number,
        title_raw=title_raw,
        headers=headers,
        rows=grid_rows,
        source="visual_grid",
        basis=basis,
        unit_caption=unit_caption,
        footnotes=[],
        bbox=(clip.x0, clip.y0, clip.x1, clip.y1),
    )


def extract_financial_tables_from_page(
    page: pymupdf.Page,
) -> list[ExtractedFinTable]:
    """페이지에서 주요 재무지표 표를 추출한다 (없으면 빈 목록)."""
    all_lines = extract_visual_lines(page)
    heading = find_heading_line(all_lines, FINANCIAL_TITLE_PATTERNS)
    if not heading:
        return []

    regions = detect_page_regions(page)
    region = regions.region_for_x((heading.x0 + heading.x1) / 2)
    end_y = find_section_end_y(
        all_lines,
        heading,
        FINANCIAL_END_PATTERNS,
        region=region,
    )
    soft_end = end_y if end_y is not None else page.rect.height
    clip = regions.clip_for_heading(
        heading,
        page=page,
        end_y=soft_end,
    )

    near_texts = [
        line.text
        for line in all_lines
        if abs(line.y0 - heading.y0) < 40
        and region.x0 <= (line.x0 + line.x1) / 2 <= region.x1
    ]
    unit_caption = _detect_unit_caption(near_texts)
    basis_hint = _detect_basis(near_texts)

    tables: list[ExtractedFinTable] = []
    try:
        finder = page.find_tables(clip=clip)
        candidates = list(finder.tables)
    except Exception:
        candidates = []

    for table in candidates:
        if not _table_overlaps_clip(table, clip):
            continue
        extracted = _from_pymupdf_table(
            table,
            page_number=page.number + 1,
            title_raw=heading.text,
            unit_caption=unit_caption,
            basis_hint=basis_hint,
        )
        if extracted:
            tables.append(extracted)

    if not tables:
        visual = _visual_fin_grid(
            page,
            clip,
            page_number=page.number + 1,
            title_raw=heading.text,
            unit_caption=unit_caption,
            basis=basis_hint,
        )
        if visual:
            tables.append(visual)

    for table in tables:
        bottom = table.bbox[3] if table.bbox else clip.y1
        table.footnotes = _extract_footnotes(all_lines, bottom)

    return tables


def extract_financial_tables_from_document(
    document: pymupdf.Document,
    *,
    max_pages: int,
) -> list[ExtractedFinTable]:
    tables: list[ExtractedFinTable] = []
    page_count = min(max_pages, len(document))
    for index in range(page_count):
        tables.extend(extract_financial_tables_from_page(document[index]))
    return tables
