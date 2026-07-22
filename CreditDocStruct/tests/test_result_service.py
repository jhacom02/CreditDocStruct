"""result_service 전용 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from admin.services.result_service import (
    ResultServiceError,
    build_excel_bytes,
    build_summary_rows,
    filter_results,
    list_result_files,
    load_results_json,
)
from common.fail_reasons import message_for
from common.settings import get_instruments_config
from export.excel import EXCEL_COLUMNS


def test_empty_result_dir(tmp_path: Path) -> None:
    assert list_result_files(tmp_path) == []


def test_load_non_list_json(tmp_path: Path) -> None:
    path = tmp_path / "obj.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(ResultServiceError):
        load_results_json(path)


def test_summary_rows_include_fail_reason() -> None:
    results = [
        {
            "result_no": 1,
            "file_name": "x.pdf",
            "company_name": "A",
            "agency": "NICE신용평가㈜",
            "status": "fail",
            "fail_reason": {"code": "parse_error", "message": "파싱 실패"},
            "products": [],
        }
    ]
    rows = build_summary_rows(results, get_instruments_config())
    assert rows[0]["실패코드"] == "parse_error"
    assert rows[0]["실패사유"] == f"parse_error — {message_for('parse_error')}"


def test_excel_bytes_row_count_matches_filter() -> None:
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
            "file_name": "fail.pdf",
            "company_name": "실패사",
            "agency": "한국신용평가㈜",
            "status": "fail",
            "products": [],
            "fail_reason": {"code": "rating_not_found", "message": "등급 없음"},
        },
    ]
    filtered = filter_results(results, status="success")
    payload = build_excel_bytes(filtered, get_instruments_config())
    assert payload[:2] == b"PK"

    from io import BytesIO

    import pandas as pd

    dataframe = pd.read_excel(BytesIO(payload))
    assert list(dataframe.columns) == EXCEL_COLUMNS
    assert len(dataframe) == 2
