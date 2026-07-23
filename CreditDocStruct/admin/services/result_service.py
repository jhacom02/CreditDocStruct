"""결과 JSON 로드·필터·Excel 바이트 생성."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agency.agency import AGENCY_DISPLAY_NAMES
from common.settings import InstrumentsConfig, get_settings
from export.excel import build_excel_public_rows, write_results_excel_tmp

AGENCY_FILTER_OPTIONS: tuple[str, ...] = (
    "전체",
    *(AGENCY_DISPLAY_NAMES[key] for key in ("nice", "kis", "kr")),
)


class ResultServiceError(ValueError):
    """결과 파일 로드·검증 실패."""


@dataclass(frozen=True)
class ResultFileInfo:
    path: Path
    name: str
    modified_at: float


@dataclass(frozen=True)
class PublicRowSource:
    """공개 신용등급 행 + 원본 PDF 결과."""

    row: dict[str, Any]
    result: dict[str, Any]


def list_result_files(result_dir: Path | None = None) -> list[ResultFileInfo]:
    base = result_dir or get_settings().result_dir_path
    if not base.exists():
        return []
    files = [
        ResultFileInfo(
            path=path,
            name=path.name,
            modified_at=path.stat().st_mtime,
        )
        for path in base.glob("*.json")
        if path.is_file()
    ]
    return sorted(files, key=lambda item: item.modified_at, reverse=True)


def load_results_json(path: Path) -> list[dict[str, Any]]:
    import json

    if not path.exists():
        raise ResultServiceError("선택한 결과 파일을 찾을 수 없습니다.")
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except UnicodeDecodeError as exc:
        raise ResultServiceError("결과 파일 인코딩을 읽을 수 없습니다.") from exc
    except json.JSONDecodeError as exc:
        raise ResultServiceError(
            "결과 파일이 손상되었거나 JSON 형식이 아닙니다."
        ) from exc

    if not isinstance(data, list):
        raise ResultServiceError("결과 파일은 JSON 배열이어야 합니다.")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ResultServiceError(
                f"결과 항목 {index + 1}번이 객체가 아닙니다."
            )
    return data


def filter_results(
    results: list[dict[str, Any]],
    *,
    agency: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    agency = (agency or "").strip()
    query = (query or "").strip().lower()

    filtered: list[dict[str, Any]] = []
    for item in results:
        if agency and agency != "전체" and item.get("agency") != agency:
            continue
        if query:
            company = str(item.get("company_name") or "").lower()
            if query not in company:
                continue
        filtered.append(item)
    return filtered


def summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    success = sum(1 for item in results if item.get("status") == "success")
    partial = sum(1 for item in results if item.get("status") == "partial")
    fail = sum(1 for item in results if item.get("status") == "fail")
    return {
        "total": len(results),
        "success": success,
        "partial": partial,
        "fail": fail,
    }


def build_public_rows_with_sources(
    results: list[dict[str, Any]],
    config: InstrumentsConfig,
) -> list[PublicRowSource]:
    pairs: list[PublicRowSource] = []
    for item in results:
        for row in build_excel_public_rows(item, config):
            pairs.append(PublicRowSource(row=row, result=item))
    return pairs


def build_public_rows(
    results: list[dict[str, Any]],
    config: InstrumentsConfig,
) -> list[dict[str, Any]]:
    return [pair.row for pair in build_public_rows_with_sources(results, config)]


def empty_financial_wide_rows() -> list[dict[str, Any]]:
    """미선택 시 빈 재무지표 표 (계정과목 열만)."""
    return []


def empty_financial_wide_columns() -> list[str]:
    return ["계정과목"]


def financial_table_to_wide_rows(
    table: dict[str, Any] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """raw financial_tables 항목 → (열이름, wide 행).

    열1=계정과목, 이후=기간 헤더. 유효 행이 없으면 빈 목록.
    """
    if not table:
        return empty_financial_wide_columns(), []

    headers = list(table.get("headers") or [])
    rows = list(table.get("rows") or [])
    period_headers: list[str] = []
    for index, header in enumerate(headers[1:], start=1):
        label = str(header or "").strip()
        if not label:
            label = f"기간{index}"
        period_headers.append(label)

    columns = ["계정과목", *period_headers]
    wide_rows: list[dict[str, Any]] = []
    for row in rows:
        cells = list(row or [])
        if not cells:
            continue
        account = str(cells[0] if cells else "").strip()
        if not account:
            continue
        entry: dict[str, Any] = {"계정과목": account}
        for col_index, col_name in enumerate(period_headers):
            value_index = col_index + 1
            if value_index < len(cells):
                entry[col_name] = cells[value_index]
            else:
                entry[col_name] = ""
        wide_rows.append(entry)

    if not wide_rows:
        return empty_financial_wide_columns(), []
    return columns, wide_rows


def financial_fail_message(result: dict[str, Any]) -> str:
    agency = str(result.get("agency") or "신평사")
    company = str(result.get("company_name") or "기업")
    return f"{agency}에서 제공하는 {company} 재무지표 추출에 실패했습니다."


def first_financial_table(
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not result:
        return None
    tables = result.get("financial_tables") or []
    if not tables:
        return None
    first = tables[0]
    return first if isinstance(first, dict) else None


def build_public_excel_bytes(
    results: list[dict[str, Any]],
    config: InstrumentsConfig,
) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        final_path = Path(tmpdir) / "download.xlsx"
        tmp_path = write_results_excel_tmp(results, config, final_path)
        return tmp_path.read_bytes()
