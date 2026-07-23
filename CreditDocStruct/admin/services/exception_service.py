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
                    "action": "원본 PDF 파싱에 실패했습니다.",
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
                        "「상품 사전」탭에서 해당 원문 라벨을 추가한 뒤 추출을 다시 실행하세요."
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
                        "신용등급을 인식할 수 없습니다. 원문을 확인한 뒤 수기 입력해주세요."
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
                        "특정 신평사의 재무지표가 없거나 추출에 실패했습니다. 원문을 확인한 뒤 수기 입력해주세요."
                    ),
                }
            )

    return items


def count_exceptions(results: list[dict[str, Any]]) -> int:
    return len(collect_exceptions(results))
