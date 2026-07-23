"""exception_service 단위 테스트."""

from __future__ import annotations

from admin.services.exception_service import (
    EXCEPTION_FILE_ERROR,
    EXCEPTION_NO_FINANCIAL,
    EXCEPTION_RATING_AMBIGUOUS,
    EXCEPTION_UNDEFINED,
    collect_exceptions,
    count_exceptions,
)


def test_collect_exceptions_categories() -> None:
    results = [
        {
            "result_no": 1,
            "file_name": "a.pdf",
            "company_name": "갑",
            "agency": "NICE신용평가㈜",
            "fail_reason": None,
            "undefined_records": [
                {"raw_label": "신표현", "rating": "A+", "normalized_label": "신표현"},
                {"raw_label": "등급없음", "rating": None},
            ],
            "products": [
                {
                    "raw_label": "발행자",
                    "instrument_key": "issuer",
                    "fail_reason": {
                        "code": "multiple_ratings",
                        "message": "복수",
                    },
                }
            ],
            "financial_tables": [],
        },
        {
            "result_no": 2,
            "file_name": "b.pdf",
            "company_name": "을",
            "agency": "한국신용평가㈜",
            "fail_reason": {
                "code": "file_error",
                "message": "열 수 없음",
            },
            "undefined_records": [],
            "products": [],
            "financial_tables": [],
        },
    ]
    items = collect_exceptions(results)
    types = {item["type"] for item in items}
    assert EXCEPTION_UNDEFINED in types
    assert EXCEPTION_RATING_AMBIGUOUS in types
    assert EXCEPTION_NO_FINANCIAL in types
    assert EXCEPTION_FILE_ERROR in types
    undefined = [i for i in items if i["type"] == EXCEPTION_UNDEFINED]
    assert len(undefined) == 1
    assert undefined[0]["detail"] == "신표현"
    # file_error 건은 재무 표 없음 중복 집계하지 않음
    file_items = [i for i in items if i["result_no"] == 2]
    assert len(file_items) == 1
    assert count_exceptions(results) == len(items)


def test_collect_exceptions_empty() -> None:
    results = [
        {
            "result_no": 1,
            "file_name": "ok.pdf",
            "company_name": "병",
            "agency": "한국기업평가㈜",
            "fail_reason": None,
            "undefined_records": [],
            "products": [{"fail_reason": None}],
            "financial_tables": [{"rows": []}],
        }
    ]
    assert collect_exceptions(results) == []
