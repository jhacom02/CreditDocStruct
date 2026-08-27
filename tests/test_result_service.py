"""result_service 전용 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from admin.services.result_service import (
    ResultServiceError,
    build_public_excel_bytes,
    build_public_rows,
    build_public_rows_with_sources,
    empty_financial_wide_columns,
    filter_results,
    financial_fail_message,
    financial_table_to_wide_rows,
    list_result_files,
    load_results_json,
)
from common.settings import get_instruments_config
from export.excel import EXCEL_PUBLIC_COLUMNS


def test_empty_result_dir(tmp_path: Path) -> None:
    assert list_result_files(tmp_path) == []


def test_load_non_list_json(tmp_path: Path) -> None:
    path = tmp_path / "obj.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(ResultServiceError):
        load_results_json(path)


def test_public_rows_use_public_columns() -> None:
    results = [
        {
            "result_no": 1,
            "file_name": "x.pdf",
            "company_name": "A",
            "agency": "NICE신용평가㈜",
            "status": "success",
            "fail_reason": None,
            "products": [
                {
                    "instrument_key": "issuer",
                    "raw_label": "발행자",
                    "rating": "AAA",
                    "outlook": "안정적",
                    "evaluation_type": "본",
                    "status": "success",
                    "fail_reason": None,
                }
            ],
        }
    ]
    rows = build_public_rows(results, get_instruments_config())
    assert len(rows) == 1
    assert set(rows[0].keys()) == set(EXCEL_PUBLIC_COLUMNS)


def test_filter_results_by_agency() -> None:
    results = [
        {
            "company_name": "A사",
            "agency": "NICE신용평가㈜",
            "status": "success",
        },
        {
            "company_name": "B사",
            "agency": "한국신용평가㈜",
            "status": "success",
        },
    ]
    assert len(filter_results(results, agency="전체")) == 2
    nice = filter_results(results, agency="NICE신용평가㈜")
    assert len(nice) == 1
    assert nice[0]["company_name"] == "A사"
    assert filter_results(results, agency="한국기업평가㈜") == []


def test_build_public_rows_with_sources_maps_result() -> None:
    results = [
        {
            "result_no": 1,
            "file_name": "x.pdf",
            "company_name": "A",
            "agency": "NICE신용평가㈜",
            "status": "success",
            "financial_tables": [{"headers": ["", "2024"], "rows": [["총자산", "1"]]}],
            "products": [
                {
                    "instrument_key": "issuer",
                    "raw_label": "발행자",
                    "rating": "AAA",
                    "outlook": "안정적",
                    "evaluation_type": "본",
                    "status": "success",
                    "fail_reason": None,
                }
            ],
        }
    ]
    pairs = build_public_rows_with_sources(results, get_instruments_config())
    assert len(pairs) == 1
    assert pairs[0].result is results[0]
    assert pairs[0].row["회사명"] == "A"


def test_financial_table_to_wide_rows() -> None:
    columns, rows = financial_table_to_wide_rows(
        {
            "headers": ["", "2023.12", "2024.12"],
            "rows": [
                ["총자산", "100", "200"],
                ["자기자본", "10", "20"],
            ],
        }
    )
    assert columns == ["계정과목", "2023.12", "2024.12"]
    assert rows[0]["계정과목"] == "총자산"
    assert rows[0]["2024.12"] == "200"
    assert rows[1]["계정과목"] == "자기자본"
    assert rows[1]["2023.12"] == "10"

    empty_cols, empty_rows = financial_table_to_wide_rows(None)
    assert empty_cols == empty_financial_wide_columns()
    assert empty_rows == []

    blank_cols, blank_rows = financial_table_to_wide_rows(
        {"headers": ["구분"], "rows": []}
    )
    assert blank_cols == ["계정과목"]
    assert blank_rows == []


def test_financial_fail_message() -> None:
    msg = financial_fail_message(
        {"agency": "한국신용평가㈜", "company_name": "(주)테스트"}
    )
    assert msg == "한국신용평가㈜에서 제공하는 (주)테스트 재무지표 추출에 실패했습니다."


def test_public_excel_bytes_row_count_matches_filter() -> None:
    results = [
        {
            "result_no": 1,
            "file_name": "ok.pdf",
            "company_name": "성공사",
            "agency": "한국신용평가㈜",
            "status": "success",
            "products": [
                {
                    "instrument_key": "issuer",
                    "raw_label": "발행자",
                    "rating": "AAA",
                    "outlook": "안정적",
                    "evaluation_type": "본",
                    "status": "success",
                    "fail_reason": None,
                },
                {
                    "instrument_key": "coco_t1",
                    "raw_label": "신종자본증권",
                    "rating": "A+",
                    "outlook": "안정적",
                    "evaluation_type": "정기",
                    "status": "success",
                    "fail_reason": None,
                },
            ],
        },
        {
            "result_no": 2,
            "file_name": "other.pdf",
            "company_name": "다른사",
            "agency": "NICE신용평가㈜",
            "status": "success",
            "products": [
                {
                    "instrument_key": "issuer",
                    "raw_label": "발행자",
                    "rating": "AA",
                    "outlook": "안정적",
                    "evaluation_type": "본",
                    "status": "success",
                    "fail_reason": None,
                }
            ],
        },
    ]
    filtered = filter_results(results, agency="한국신용평가㈜")
    payload = build_public_excel_bytes(filtered, get_instruments_config())
    assert payload[:2] == b"PK"

    from io import BytesIO

    import pandas as pd

    with pd.ExcelFile(BytesIO(payload)) as workbook:
        assert len(workbook.sheet_names) >= 2
        dataframe = pd.read_excel(workbook, sheet_name="신용등급")
    assert list(dataframe.columns) == EXCEL_PUBLIC_COLUMNS
    assert len(dataframe) == 2
