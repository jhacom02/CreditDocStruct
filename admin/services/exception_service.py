"""결과 JSON 기반 확인 필요(예외) 대기열."""

from __future__ import annotations

from typing import Any

from common.fail_reasons import (
    FILE_ERROR,
    MULTIPLE_RATING_COLUMNS,
    MULTIPLE_RATINGS,
    PARSE_ERROR,
    TEXT_EXTRACTION_FAILED,
)

EXCEPTION_UNDEFINED = "undefined_label"
EXCEPTION_RATING_AMBIGUOUS = "rating_ambiguous"
EXCEPTION_NO_FINANCIAL = "no_financial_table"
EXCEPTION_FILE_ERROR = "file_or_parse_error"

_RATING_AMBIGUOUS_CODES = frozenset(
    {MULTIPLE_RATING_COLUMNS, MULTIPLE_RATINGS}
)
_FILE_ERROR_CODES = frozenset(
    {FILE_ERROR, TEXT_EXTRACTION_FAILED, PARSE_ERROR}
)


def _fail_code(value: Any) -> str | None:
    if isinstance(value, dict):
        code = value.get("code")
        return str(code) if code else None
    return None


def collect_exceptions(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for result in results:
        file_name = result.get("file_name") or ""
        company = result.get("company_name") or ""
        agency = result.get("agency") or ""
        result_no = result.get("result_no")

        pdf_code = _fail_code(result.get("fail_reason"))
        if pdf_code in _FILE_ERROR_CODES:
            items.append(
                {
                    "type": EXCEPTION_FILE_ERROR,
                    "type_label": "파일/텍스트/구조 오류",
                    "file_name": file_name,
                    "company_name": company,
                    "agency": agency,
                    "result_no": result_no,
                    "detail": pdf_code,
                    "message": (result.get("fail_reason") or {}).get("message")
                    or "",
                    "action": (
                        "PDF를 다시 받거나 손상·암호 여부를 확인한 뒤, 추출을 다시 실행하세요."
                    ),
                }
            )

        for record in result.get("undefined_records") or []:
            if not record.get("rating"):
                continue
            items.append(
                {
                    "type": EXCEPTION_UNDEFINED,
                    "type_label": "미분류 상품",
                    "file_name": file_name,
                    "company_name": company,
                    "agency": agency,
                    "result_no": result_no,
                    "detail": record.get("raw_label")
                    or record.get("normalized_label")
                    or "",
                    "message": "",
                    "action": (
                        "상세의 원문표현을 복사해 「상품 사전」에서 맞는 상품을 "
                        "고른 뒤 추가하고, 재추출하세요."
                    ),
                    "rating": record.get("rating"),
                }
            )

        for product in result.get("products") or []:
            code = _fail_code(product.get("fail_reason"))
            if code not in _RATING_AMBIGUOUS_CODES:
                continue
            items.append(
                {
                    "type": EXCEPTION_RATING_AMBIGUOUS,
                    "type_label": "신용등급 모호/충돌",
                    "file_name": file_name,
                    "company_name": company,
                    "agency": agency,
                    "result_no": result_no,
                    "detail": product.get("raw_label")
                    or product.get("instrument_key")
                    or "",
                    "message": (product.get("fail_reason") or {}).get("message")
                    or code
                    or "",
                    "action": (
                        "원문 PDF를 보고 수기로 보완하세요. "
                        "같은 문제가 반복되면 개발에 요청하세요."
                    ),
                }
            )

        fin_tables = result.get("financial_tables") or []
        if not fin_tables and pdf_code not in _FILE_ERROR_CODES:
            items.append(
                {
                    "type": EXCEPTION_NO_FINANCIAL,
                    "type_label": "재무지표 없음",
                    "file_name": file_name,
                    "company_name": company,
                    "agency": agency,
                    "result_no": result_no,
                    "detail": "",
                    "message": "",
                    "action": (
                        "해당 신평사 자료에 표가 없거나 읽히지 않은 경우입니다. "
                        "수기 보완하거나 개발에 요청하세요."
                    ),
                }
            )

    return items


def count_exceptions(results: list[dict[str, Any]]) -> int:
    return len(collect_exceptions(results))
