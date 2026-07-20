"""비개발자용 Excel 저장 (신용등급_결과, PDF당 1행).

Plan: creditratefinder_restructure_43c68190 섹션 F 참고.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.settings import InstrumentsConfig


EXCEL_COLUMNS = [
    "결과_ID",
    "회사명",
    "신평사",
    "처리상태",
    "대분류_Key",
    "대분류명",
    "소분류_원본라벨",
    "신용등급",
    "등급전망",
    "원본파일명",
]


def build_excel_row(
    result: dict[str, Any],
    config: InstrumentsConfig,
) -> dict[str, Any]:
    selected = result.get("selected") or {}
    status = result.get("status")
    instrument_key = selected.get("instrument_key") if selected else None

    major_name = ""
    if status == "success" and instrument_key:
        definition = config.instruments.get(instrument_key)
        major_name = definition.major_category_name if definition else ""

    if status == "success" and selected:
        return {
            "결과_ID": result.get("result_id", ""),
            "회사명": result.get("company_name", ""),
            "신평사": result.get("agency", ""),
            "처리상태": status,
            "대분류_Key": instrument_key or "",
            "대분류명": major_name,
            "소분류_원본라벨": selected.get("raw_label") or "",
            "신용등급": selected.get("rating") or "",
            "등급전망": selected.get("outlook") or "",
            "원본파일명": result.get("file_name", ""),
        }

    return {
        "결과_ID": result.get("result_id", ""),
        "회사명": result.get("company_name", ""),
        "신평사": result.get("agency", ""),
        "처리상태": status or "fail",
        "대분류_Key": "",
        "대분류명": "",
        "소분류_원본라벨": "",
        "신용등급": "",
        "등급전망": "",
        "원본파일명": result.get("file_name", ""),
    }


def write_results_excel_tmp(
    results: list[dict[str, Any]],
    config: InstrumentsConfig,
    final_path: str | Path,
) -> Path:
    """`final_path.tmp`에 Excel을 쓰고 tmp 경로를 반환한다."""
    import pandas as pd

    final_path = Path(final_path)
    tmp_path = final_path.with_name(final_path.name + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [build_excel_row(result, config) for result in results]
    dataframe = pd.DataFrame(rows, columns=EXCEL_COLUMNS)

    with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="신용등급_결과", index=False)
        worksheet = writer.book["신용등급_결과"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        for column_cells in worksheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter
            for cell in column_cells:
                value = "" if cell.value is None else str(cell.value)
                max_length = max(max_length, len(value))
            worksheet.column_dimensions[column_letter].width = min(
                max(max_length + 2, 10),
                60,
            )

    return tmp_path
