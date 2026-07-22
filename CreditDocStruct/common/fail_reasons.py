"""fail_reason code·message 상수 및 우선순위.

문구는 별도 YAML/JSON으로 분리하지 않고 코드 상수로만 둔다.
PDF급 오류는 `PRIORITY_ORDER` 위→아래 순서로 매기고,
상품급 오류(`multiple_rating_columns` 등)는 products[].fail_reason에 둔다.
"""

from __future__ import annotations

from typing import Final

FILE_ERROR: Final[str] = "file_error"
TEXT_EXTRACTION_FAILED: Final[str] = "text_extraction_failed"
PARSE_ERROR: Final[str] = "parse_error"
MULTIPLE_RATING_COLUMNS: Final[str] = "multiple_rating_columns"
MULTIPLE_RATINGS: Final[str] = "multiple_ratings"
RATING_NOT_FOUND: Final[str] = "rating_not_found"
LABEL_NOT_FOUND: Final[str] = "label_not_found"
UNDEFINED_LABEL: Final[str] = "undefined_label"

# PDF급 오류 우선순위 (위→아래). 상품 복수(multiple_instruments)는 제거됨.
PRIORITY_ORDER: Final[tuple[str, ...]] = (
    FILE_ERROR,
    TEXT_EXTRACTION_FAILED,
    PARSE_ERROR,
    MULTIPLE_RATING_COLUMNS,
    MULTIPLE_RATINGS,
    RATING_NOT_FOUND,
    LABEL_NOT_FOUND,
    UNDEFINED_LABEL,
)

_MESSAGES: Final[dict[str, str]] = {
    FILE_ERROR: "PDF 파일을 열 수 없습니다(손상, 암호 설정 등 파일 열기 실패).",
    TEXT_EXTRACTION_FAILED: (
        "PDF에서 평가에 쓸 텍스트·등급 토큰을 충분히 추출하지 못했습니다."
    ),
    PARSE_ERROR: (
        "PDF는 읽었지만 평가대상 행 또는 표 구조를 구성하지 못했습니다."
    ),
    MULTIPLE_RATING_COLUMNS: (
        "현재등급 열을 적용한 뒤에도 신용등급을 하나로 확정할 수 없습니다."
    ),
    MULTIPLE_RATINGS: (
        "동일 상품에 대해 서로 다른 신용등급 또는 등급전망이 복수 "
        "검출되었습니다."
    ),
    RATING_NOT_FOUND: (
        "평가대상 라벨은 YAML에 정상 매칭되었지만 신용등급을 추출하지 "
        "못했습니다."
    ),
    LABEL_NOT_FOUND: (
        "신용등급은 검출되었지만 대응하는 평가대상 라벨을 추출하지 "
        "못했습니다."
    ),
    UNDEFINED_LABEL: (
        "신용등급이 있는 평가대상 라벨이 YAML label_dictionary에 "
        "등록되지 않았습니다."
    ),
}


def message_for(code: str) -> str:
    try:
        return _MESSAGES[code]
    except KeyError as error:
        raise ValueError(f"알 수 없는 fail_reason code: {code!r}") from error


def make_fail_reason(code: str) -> dict[str, str]:
    """`{"code", "message"}` 형태의 fail_reason 객체를 만든다."""
    return {"code": code, "message": message_for(code)}


ALL_CODES: Final[tuple[str, ...]] = PRIORITY_ORDER
