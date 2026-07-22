"""결과 JSON 로드·필터·Excel 바이트 생성."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.settings import InstrumentsConfig, get_settings
from export.excel import build_excel_public_rows, write_results_excel_tmp


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


def filter_results(
    results: list[dict[str, Any]],
    *,
    status: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    status = (status or "").strip()
    query = (query or "").strip().lower()

    filtered: list[dict[str, Any]] = []
    for item in results:
        if status and status != "전체" and item.get("status") != status:
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


def build_public_rows(
    results: list[dict[str, Any]],
    config: InstrumentsConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        rows.extend(build_excel_public_rows(item, config))
    return rows


def build_public_excel_bytes(
    results: list[dict[str, Any]],
    config: InstrumentsConfig,
) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        final_path = Path(tmpdir) / "download.xlsx"
        tmp_path = write_results_excel_tmp(results, config, final_path)
        return tmp_path.read_bytes()
