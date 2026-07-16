from __future__ import annotations

from pathlib import Path
from typing import Any


def build_summary_row(result: dict[str, Any]) -> dict[str, Any]:
    selected = result.get("selected") or {}
    ratings = result.get("ratings") or {}

    return {
        "파일명": result["file_name"],
        "파일경로": result["file_path"],
        "신용평가사": result["agency"],
        "처리상태": result["status"],
        "목표상품": result["target_instrument"],
        "선택상품유형": selected.get("instrument_type"),
        "선택레이블": selected.get("raw_label"),
        "평가종류": selected.get("evaluation_type"),
        "현재등급": selected.get("current_rating"),
        "등급전망": selected.get("current_outlook"),
        "현재등급_표시": selected.get("current_rating_display"),
        "직전등급": selected.get("previous_rating"),
        "직전등급전망": selected.get("previous_outlook"),
        "직전등급_표시": selected.get("previous_rating_display"),
        "Rating Action": selected.get("rating_action"),
        "비고": selected.get("remark"),
        "종목명": selected.get("issue_name"),
        "페이지": selected.get("page"),
        "추출출처": selected.get("source"),
        "신뢰도": selected.get("confidence"),
        "기업신용등급": ratings.get("issuer", {}).get(
            "current_rating_display"
        ),
        "무보증사채등급": ratings.get("senior_unsecured", {}).get(
            "current_rating_display"
        ),
        "CoCo_T2등급": ratings.get("coco_t2", {}).get(
            "current_rating_display"
        ),
        "CoCo_T1등급": ratings.get("coco_t1", {}).get(
            "current_rating_display"
        ),
        "기업어음등급": ratings.get("commercial_paper", {}).get(
            "current_rating_display"
        ),
        "전자단기사채등급": ratings.get("short_term_bond", {}).get(
            "current_rating_display"
        ),
        "리뷰건수": len(result.get("review_records") or []),
        "추출문맥": selected.get("raw_text"),
    }


def build_detail_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for record in result.get("records", []):
        rows.append(
            {
                "파일명": result["file_name"],
                "신용평가사": result["agency"],
                "페이지": record.get("page"),
                "섹션": record.get("section"),
                "추출출처": record.get("source"),
                "평가대상레이블": record.get("raw_label"),
                "상품유형": record.get("instrument_type"),
                "분류상태": record.get("classification_status"),
                "분류점수": record.get("classification_score"),
                "분류특징": record.get("classification_features"),
                "평가종류": record.get("evaluation_type"),
                "현재등급": record.get("current_rating"),
                "등급전망": record.get("current_outlook"),
                "현재등급_표시": record.get("current_rating_display"),
                "직전등급": record.get("previous_rating"),
                "직전등급전망": record.get("previous_outlook"),
                "직전등급_표시": record.get("previous_rating_display"),
                "Rating Action": record.get("rating_action"),
                "비고": record.get("remark"),
                "종목명": record.get("issue_name"),
                "신뢰도": record.get("confidence"),
                "원문": record.get("raw_text"),
            }
        )

    return rows


def write_results_workbook(
    output_excel: str | Path,
    summary_rows: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
) -> Path:
    import pandas as pd

    output_excel = Path(output_excel)
    output_excel.parent.mkdir(parents=True, exist_ok=True)

    summary_df = pd.DataFrame(summary_rows)
    detail_df = pd.DataFrame(detail_rows)
    review_df = pd.DataFrame(review_rows)

    with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        detail_df.to_excel(writer, sheet_name="all_candidates", index=False)
        review_df.to_excel(writer, sheet_name="needs_review", index=False)

        for worksheet in writer.book.worksheets:
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

    return output_excel
