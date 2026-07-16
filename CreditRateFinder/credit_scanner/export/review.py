from __future__ import annotations

from typing import Any

from credit_scanner.text_utils import compact_text, normalize_text


def build_review_rows(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    review_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for result in results:
        for record in result.get("review_records") or []:
            label = normalize_text(record.get("raw_label") or "")
            key = (compact_text(label), record.get("instrument_type") or "")

            if key in seen:
                continue

            seen.add(key)
            review_rows.append(
                {
                    "파일명": result.get("file_name"),
                    "신용평가사": result.get("agency"),
                    "평가대상레이블": label,
                    "분류상태": record.get("classification_status"),
                    "현재추정유형": record.get("instrument_type"),
                    "추천후보": record.get("classification_runner_up"),
                    "특징": record.get("classification_features"),
                    "점수": record.get("classification_score"),
                    "현재등급": record.get("current_rating_display"),
                    "원문": record.get("raw_text"),
                    "제안_canonical_type": "",
                    "제안_alias": label,
                    "메모": "taxonomy YAML aliases에 추가 후 재실행",
                }
            )

    return review_rows


def suggest_taxonomy_aliases(
    review_csv_or_rows: list[dict[str, Any]],
) -> list[str]:
    """승인된 별칭을 taxonomy YAML에 넣을 스니펫으로 변환."""
    lines: list[str] = []

    for row in review_csv_or_rows:
        canonical = (row.get("제안_canonical_type") or "").strip()
        alias = (
            row.get("제안_alias") or row.get("평가대상레이블") or ""
        ).strip()

        if not canonical or not alias:
            continue

        lines.append(f"  # add under instruments.{canonical}.aliases:")
        lines.append(f'  - "{alias}"')

    return lines
