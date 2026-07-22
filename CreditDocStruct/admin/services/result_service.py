"""결과 JSON 로드·필터·Excel 바이트 생성."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.fail_reasons import message_for
from common.settings import InstrumentsConfig, get_settings
from export.excel import EXCEL_COLUMNS, build_excel_rows


class ResultServiceError(ValueError):
    """결과 파일 로드·검증 실패."""


@dataclass(frozen=True)
class ResultFileInfo:
    path: Path
    name: str
    modified_at: float


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


def _product_keys(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for product in item.get("products") or []:
        key = product.get("instrument_key")
        if key:
            keys.add(key)
    return keys


def _item_fail_codes(item: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    reason = item.get("fail_reason") or {}
    if isinstance(reason, dict) and reason.get("code"):
        codes.add(reason["code"])
    for product in item.get("products") or []:
        product_reason = product.get("fail_reason") or {}
        if isinstance(product_reason, dict) and product_reason.get("code"):
            codes.add(product_reason["code"])
    return codes


def filter_results(
    results: list[dict[str, Any]],
    *,
    status: str | None = None,
    agency: str | None = None,
    instrument_key: str | None = None,
    fail_code: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    status = (status or "").strip()
    agency = (agency or "").strip()
    instrument_key = (instrument_key or "").strip()
    fail_code = (fail_code or "").strip()
    query = (query or "").strip().lower()

    filtered: list[dict[str, Any]] = []
    for item in results:
        if status and status != "전체" and item.get("status") != status:
            continue
        if agency and agency != "전체" and (item.get("agency") or "") != agency:
            continue

        if instrument_key and instrument_key != "전체":
            if instrument_key not in _product_keys(item):
                continue

        if fail_code and fail_code != "전체":
            if fail_code not in _item_fail_codes(item):
                continue

        if query:
            haystack = " ".join(
                [
                    str(item.get("company_name") or ""),
                    str(item.get("file_name") or ""),
                    str(item.get("agency") or ""),
                ]
            ).lower()
            if query not in haystack:
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


def build_summary_rows(
    results: list[dict[str, Any]],
    config: InstrumentsConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        pdf_reason = item.get("fail_reason") or {}
        for row in build_excel_rows(item, config):
            code = row.get("실패사유") or ""
            if not code and isinstance(pdf_reason, dict):
                code = pdf_reason.get("code") or ""
            message = ""
            if code:
                try:
                    message = message_for(code)
                except ValueError:
                    if (
                        isinstance(pdf_reason, dict)
                        and pdf_reason.get("code") == code
                    ):
                        message = pdf_reason.get("message") or ""
            row["실패코드"] = code
            row["실패사유"] = f"{code} — {message}" if message else code
            rows.append(row)
    return rows


def build_excel_bytes(
    results: list[dict[str, Any]],
    config: InstrumentsConfig,
) -> bytes:
    from export.excel import write_admin_excel_bytes

    return write_admin_excel_bytes(results, config)


def result_identity(item: dict[str, Any]) -> str:
    file_hash = item.get("file_hash") or ""
    file_name = item.get("file_name") or ""
    result_no = item.get("result_no")
    return f"{file_hash}|{file_name}|{result_no}"
