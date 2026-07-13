"""신용평가서 PDF에서 평가대상별 신용등급을 추출하는 패키지."""

from credit_scanner.pipeline import extract_credit_report

__all__ = [
    "extract_credit_report",
]

__version__ = "1.0.0"
