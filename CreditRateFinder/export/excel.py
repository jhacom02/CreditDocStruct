"""비개발자용 Excel 저장 (신용등급_결과, 상품당 1행).

Plan: creditratefinder_restructure_43c68190 섹션 F 참고.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.settings import InstrumentsConfig


EXCEL_COLUMNS = [
    "No",
    "회사명",
    "신평사",
    "처리상태",
    "상품분류_Key",
    "상품분류",
    "원본라벨",
    "평가종류",
    "신용등급",
    "등급전망",
    "원본파일명",
    "실패사유",
]


def build_excel_rows(
    result: dict[str, Any],
    config: InstrumentsConfig,
) -> list[dict[str, Any]]:
    """PDF 결과의 products를 Excel 행들로 펼친다."""
    products = result.get("products") or []
    base = {
        "No": result.get("result_no", ""),
        "회사명": result.get("company_name", ""),
        "신평사": result.get("agency", ""),
        "원본파일명": result.get("file_name", ""),
    }

    if not products:
        fail_reason = result.get("fail_reason") or {}
        return [
            {
                **base,
                "처리상태": result.get("status") or "fail",
                "상품분류_Key": "",
                "상품분류": "",
                "원본라벨": "",
                "평가종류": "",
                "신용등급": "",
                "등급전망": "",
                "실패사유": fail_reason.get("code") or "",
            }
        ]

    rows: list[dict[str, Any]] = []
    for product in products:
        instrument_key = product.get("instrument_key")
        display_name = ""
        if instrument_key:
            definition = config.instruments.get(instrument_key)
            display_name = definition.display_name if definition else ""

        fail_reason = product.get("fail_reason") or {}
        rows.append(
            {
                **base,
                "처리상태": product.get("status") or result.get("status") or "",
                "상품분류_Key": instrument_key or "",
                "상품분류": display_name,
                "원본라벨": product.get("raw_label") or "",
                "평가종류": product.get("evaluation_type") or "",
                "신용등급": product.get("rating") or "",
                "등급전망": product.get("outlook") or "",
                "실패사유": fail_reason.get("code") or "",
            }
        )
    return rows


def build_excel_row(
    result: dict[str, Any],
    config: InstrumentsConfig,
) -> dict[str, Any]:
    """하위 호환: 첫 상품 행만 반환."""
    rows = build_excel_rows(result, config)
    return rows[0]


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

    rows: list[dict[str, Any]] = []
    for result in results:
        rows.extend(build_excel_rows(result, config))
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
                max(max_length + 10, 5), 70
            )

    return tmp_path
