"""CreditRateFinder 진입점 (유일한 오케스트레이션).

CLI: python main.py <dir|pdf> [-o stem]
공개 API: from main import extract_credit_report

Plan: creditratefinder_restructure_43c68190 섹션 B/D/G-1 참고.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymupdf

from agency.agency import (
    extract_company_name,
    format_agency_display,
    resolve_agency_key,
)
from classify.classifier import LabelClassifier
from classify.undefined_filter import should_include_undefined_record
from common.fail_reasons import (
    FILE_ERROR,
    LABEL_NOT_FOUND,
    MULTIPLE_RATING_COLUMNS,
    MULTIPLE_RATINGS,
    PARSE_ERROR,
    RATING_NOT_FOUND,
    TEXT_EXTRACTION_FAILED,
    UNDEFINED_LABEL,
    make_fail_reason,
)
from common.models import ExtractedRatingRow, RatingRecord
from common.rating_tokens import find_rating_tokens_in_text
from common.settings import (
    RESULT_FILENAME_PREFIX,
    get_instruments_config,
    get_settings,
)
from extract import (
    extract_fallback_rows_from_text,
    extract_primary_rows_from_tables,
    extract_primary_rows_from_visual_layout,
    extract_valid_rating_rows,
)
from extract.row_rebuild import rebuild_merged_rows
from extract.merge import is_primary_record, merge_canonical_records, source_rank
from export.excel import write_results_excel_tmp
from export.json_io import write_results_json_tmp
from export.undefined_store import (
    file_sha256,
    make_occurrence_id,
    persist_undefined_occurrences,
)

VALID_ONLY_EVALUATION_TYPE = "유효등급"

_EVALUATION_RANK: dict[str, int] = {
    "본": 0,
    "본평가": 0,
    "수시": 1,
    "수시평가": 1,
    "신규": 2,
    "신규평가": 2,
    "예비": 3,
    "예비평가": 3,
    "정기": 4,
    "정기평가": 4,
}


def _dedupe_records(records: list[RatingRecord]) -> list[RatingRecord]:
    unique: dict[tuple[Any, ...], RatingRecord] = {}
    for record in records:
        key = (
            record.instrument_key,
            record.rating,
            record.outlook,
            record.normalized_label,
            record.page,
            record.row_index,
            record.evaluation_type,
            record.source,
        )
        unique[key] = record
    return list(unique.values())


def _evaluation_rank(record: RatingRecord) -> int:
    if record.evaluation_type in _EVALUATION_RANK:
        return _EVALUATION_RANK[record.evaluation_type]
    if is_primary_record(record):
        return 5
    return 6


def _display_evaluation_type(record: RatingRecord) -> str | None:
    if record.evaluation_type:
        return record.evaluation_type
    if is_primary_record(record):
        return None
    return VALID_ONLY_EVALUATION_TYPE


def _product_dict(
    record: RatingRecord,
    *,
    status: str,
    fail_reason: dict[str, str] | None = None,
    evaluation_type: str | None = None,
) -> dict[str, Any]:
    return {
        "instrument_key": record.instrument_key,
        "raw_label": record.raw_label,
        "normalized_label": record.normalized_label,
        "rating": record.rating if status == "success" else None,
        "outlook": record.outlook if status == "success" else None,
        "evaluation_type": (
            evaluation_type
            if evaluation_type is not None
            else _display_evaluation_type(record)
        ),
        "status": status,
        "fail_reason": fail_reason,
        "page": record.page,
        "source": record.source,
        "rating_status": record.rating_status,
        "section": record.section,
    }


def _resolve_product_group(group: list[RatingRecord]) -> dict[str, Any]:
    best_rank = min(_evaluation_rank(item) for item in group)
    candidates = [
        item for item in group if _evaluation_rank(item) == best_rank
    ]
    candidates.sort(
        key=lambda item: (
            0 if is_primary_record(item) else 1,
            source_rank(item.source),
            item.row_index,
        )
    )
    representative = candidates[0]
    evaluation_type = _display_evaluation_type(representative)

    if any(item.rating_status == "ambiguous" for item in candidates):
        return _product_dict(
            representative,
            status="fail",
            fail_reason=make_fail_reason(MULTIPLE_RATING_COLUMNS),
            evaluation_type=evaluation_type,
        )

    rated = [
        item
        for item in candidates
        if item.rating_status == "single" and item.rating
    ]
    if not rated:
        return _product_dict(
            representative,
            status="fail",
            fail_reason=make_fail_reason(RATING_NOT_FOUND),
            evaluation_type=evaluation_type,
        )

    distinct = {(item.rating, item.outlook) for item in rated}
    if len(distinct) >= 2:
        return _product_dict(
            representative,
            status="fail",
            fail_reason=make_fail_reason(MULTIPLE_RATINGS),
            evaluation_type=evaluation_type,
        )

    chosen = rated[0]
    return _product_dict(
        chosen,
        status="success",
        evaluation_type=_display_evaluation_type(chosen),
    )


def build_products(
    records: list[RatingRecord],
) -> tuple[list[dict[str, Any]], str, dict[str, str] | None]:
    """instrument_key별 상품 결과 + PDF 상태 집계.

    Returns:
        products, status (`success`|`partial`|`fail`), fail_reason
    """
    matched = [
        record
        for record in records
        if record.classification_status == "matched" and record.instrument_key
    ]

    groups: dict[str, list[RatingRecord]] = defaultdict(list)
    order: list[str] = []
    for record in matched:
        key = record.instrument_key or ""
        if key not in groups:
            order.append(key)
        groups[key].append(record)

    products: list[dict[str, Any]] = []
    rated_groups: list[list[RatingRecord]] = []
    none_groups: list[list[RatingRecord]] = []
    for key in order:
        group = groups[key]
        if any(
            item.rating_status in {"single", "ambiguous"} or item.rating
            for item in group
        ):
            rated_groups.append(group)
        else:
            none_groups.append(group)

    for group in rated_groups or none_groups:
        products.append(_resolve_product_group(group))
    success_count = sum(1 for item in products if item["status"] == "success")

    if products:
        if success_count == len(products):
            return products, "success", None
        if success_count >= 1:
            return products, "partial", None
        return products, "fail", None

    rated_rows = [
        record
        for record in records
        if record.rating_status in {"single", "ambiguous"} or record.rating
    ]
    if rated_rows:
        label_missing = any(
            not (record.raw_label or "").strip()
            or record.normalized_label == ""
            for record in rated_rows
        )
        if label_missing:
            return [], "fail", make_fail_reason(LABEL_NOT_FOUND)

        if any(
            record.classification_status == "undefined"
            for record in rated_rows
        ):
            return [], "fail", make_fail_reason(UNDEFINED_LABEL)

        return [], "fail", make_fail_reason(LABEL_NOT_FOUND)

    return [], "fail", make_fail_reason(PARSE_ERROR)


def _empty_result(
    *,
    result_no: int | None,
    file_name: str,
    file_path: str,
    company_name: str,
    agency: str,
    fail_reason: dict[str, str],
    file_hash: str | None = None,
    extracted_text_chars: int = 0,
    extracted_word_count: int = 0,
    rating_token_count: int = 0,
) -> dict[str, Any]:
    return {
        "result_no": result_no,
        "file_name": file_name,
        "file_path": file_path,
        "company_name": company_name,
        "agency": agency,
        "status": "fail",
        "fail_reason": fail_reason,
        "products": [],
        "records": [],
        "undefined_records": [],
        "validation_warnings": [],
        "extracted_text_chars": extracted_text_chars,
        "extracted_word_count": extracted_word_count,
        "rating_token_count": rating_token_count,
        "file_hash": file_hash,
    }


def _extract_rows_from_page(
    page: pymupdf.Page,
    agency_key: str,
) -> list[ExtractedRatingRow]:
    from extract.row_parser import (
        is_evaluation_only_primary_row,
        is_orphan_rating_row,
    )

    table_rows = extract_primary_rows_from_tables(page=page, agency=agency_key)
    visual_rows = extract_primary_rows_from_visual_layout(
        page=page, agency=agency_key
    )

    usable_table_rows = [
        row
        for row in table_rows
        if not is_evaluation_only_primary_row(row)
        and not is_orphan_rating_row(row)
    ]
    if usable_table_rows:
        primary_rows = table_rows
    elif visual_rows:
        primary_rows = visual_rows
    else:
        primary_rows = table_rows

    valid_rows = extract_valid_rating_rows(page=page, agency=agency_key)
    rows = list(primary_rows) + list(valid_rows)

    if not primary_rows and not valid_rows:
        rows.extend(extract_fallback_rows_from_text(page=page))

    return rows


def extract_credit_report(
    pdf_path: str | Path,
    *,
    result_no: int | None = None,
    classifier: LabelClassifier | None = None,
) -> dict[str, Any]:
    """단일 PDF를 처리해 결과 객체를 반환한다."""
    settings = get_settings()
    pdf_path = Path(pdf_path)
    active = classifier or LabelClassifier.from_yaml()

    if not pdf_path.exists():
        return _empty_result(
            result_no=result_no,
            file_name=pdf_path.name,
            file_path=str(pdf_path),
            company_name=pdf_path.stem,
            agency=format_agency_display(None),
            fail_reason=make_fail_reason(FILE_ERROR),
        )

    try:
        file_hash = file_sha256(pdf_path)
        document = pymupdf.open(pdf_path)
    except Exception:
        return _empty_result(
            result_no=result_no,
            file_name=pdf_path.name,
            file_path=str(pdf_path),
            company_name=pdf_path.stem,
            agency=format_agency_display(None),
            fail_reason=make_fail_reason(FILE_ERROR),
        )

    try:
        pages_to_check = min(settings.max_pdf_pages, len(document))
        extracted_text = ""
        for page_index in range(pages_to_check):
            extracted_text += document[page_index].get_text("text")

        extracted_text_chars = len(extracted_text.strip())
        extracted_word_count = len(extracted_text.split())
        rating_token_count = len(find_rating_tokens_in_text(extracted_text))

        first_page = document[0]
        first_page_text = first_page.get_text("text", sort=True)
        agency_key = resolve_agency_key(first_page_text, pdf_path.name)
        agency = format_agency_display(agency_key)
        company_name = extract_company_name(
            first_page,
            pdf_path.name,
            agency_key=agency_key,
        )

        extracted_rows: list[ExtractedRatingRow] = []
        for page_index in range(pages_to_check):
            extracted_rows.extend(
                _extract_rows_from_page(document[page_index], agency_key)
            )

        config = get_instruments_config()
        rebuilt_rows, rebuild_error = rebuild_merged_rows(
            extracted_rows, config
        )
        if rebuild_error:
            return _empty_result(
                result_no=result_no,
                file_name=pdf_path.name,
                file_path=str(pdf_path),
                company_name=company_name,
                agency=agency,
                fail_reason=make_fail_reason(PARSE_ERROR),
                file_hash=file_hash,
                extracted_text_chars=extracted_text_chars,
                extracted_word_count=extracted_word_count,
                rating_token_count=rating_token_count,
            )

        if not rebuilt_rows:
            if (
                extracted_text_chars < settings.min_extracted_text_chars
                and rating_token_count == 0
            ):
                fail_code = TEXT_EXTRACTION_FAILED
            else:
                fail_code = PARSE_ERROR
            return _empty_result(
                result_no=result_no,
                file_name=pdf_path.name,
                file_path=str(pdf_path),
                company_name=company_name,
                agency=agency,
                fail_reason=make_fail_reason(fail_code),
                file_hash=file_hash,
                extracted_text_chars=extracted_text_chars,
                extracted_word_count=extracted_word_count,
                rating_token_count=rating_token_count,
            )

        deduped = _dedupe_records(active.classify_rows(rebuilt_rows))
        records, validation_warnings = merge_canonical_records(deduped)
        products, status, fail_reason = build_products(deduped)

        primary_matched_labels = {
            record.normalized_label
            for record in records
            if record.classification_status == "matched"
            and is_primary_record(record)
            and record.normalized_label
        }

        undefined_records = [
            record.to_dict()
            for record in records
            if record.classification_status == "undefined"
            and should_include_undefined_record(
                record,
                primary_matched_labels=primary_matched_labels,
            )
        ]

        return {
            "result_no": result_no,
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "company_name": company_name,
            "agency": agency,
            "status": status,
            "fail_reason": fail_reason,
            "products": products,
            "validation_warnings": validation_warnings,
            "records": [record.to_dict() for record in records],
            "undefined_records": undefined_records,
            "extracted_text_chars": extracted_text_chars,
            "extracted_word_count": extracted_word_count,
            "rating_token_count": rating_token_count,
            "file_hash": file_hash,
        }
    finally:
        document.close()


def _result_stem(override: str | None = None) -> str:
    if override:
        return override
    today = date.today().strftime("%Y%m%d")
    return f"{RESULT_FILENAME_PREFIX}_{today}"


def collect_undefined_occurrences(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    for result in results:
        file_hash = result.get("file_hash")
        if not file_hash:
            continue
        for record in result.get("undefined_records") or []:
            normalized = record.get("normalized_label") or ""
            if not normalized:
                continue
            if record.get("rating_status") == "none" and not record.get("rating"):
                continue
            # YAML에 이미 matched로 등록된 라벨은 누적 제외
            # (정규화 결과가 lookup에 있으면 skip)
            config = get_instruments_config()
            if normalized in config.normalized_lookup:
                continue

            occurrence_id = make_occurrence_id(
                file_hash=file_hash,
                normalized_label=normalized,
                page=int(record.get("page") or 0),
                row_index=int(record.get("row_index") or 0),
            )
            occurrences.append(
                {
                    "occurrence_id": occurrence_id,
                    "normalized_label": normalized,
                    "raw_label": record.get("raw_label"),
                    "file_name": result.get("file_name"),
                    "company_name": result.get("company_name"),
                    "agency": result.get("agency"),
                    "rating": record.get("rating"),
                    "outlook": record.get("outlook"),
                    "evaluation_type": record.get("evaluation_type"),
                    "label_text": record.get("label_text"),
                    "suggestions": record.get("suggestions") or [],
                }
            )
    return occurrences


def commit_batch_outputs(
    results: list[dict[str, Any]],
    *,
    stem: str | None = None,
) -> tuple[Path, Path, Path]:
    """JSON·Excel·관리자 DB를 저장한다 (JSON/Excel은 tmp → 원자적 교체)."""
    settings = get_settings()
    config = get_instruments_config()

    result_stem = _result_stem(stem)
    result_dir = settings.result_dir_path
    result_dir.mkdir(parents=True, exist_ok=True)

    json_final = result_dir / f"{result_stem}.json"
    excel_final = result_dir / f"{result_stem}.xlsx"

    json_tmp = write_results_json_tmp(results, json_final)
    excel_tmp = write_results_excel_tmp(results, config, excel_final)

    db_final = persist_undefined_occurrences(
        collect_undefined_occurrences(results)
    )

    try:
        os.replace(json_tmp, json_final)
        os.replace(excel_tmp, excel_final)
    except Exception:
        for tmp in (json_tmp, excel_tmp):
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
        raise

    return json_final, excel_final, db_final


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="신용평가서 PDF에서 평가대상별 신용등급을 추출합니다.",
    )
    parser.add_argument(
        "input",
        type=str,
        nargs="?",
        default=None,
        help="PDF 파일 또는 폴더 경로 (생략 시 .env의 INPUT_DIR 사용)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="결과 파일명 stem (기본: result_YYYYMMDD)",
    )
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="폴더 입력 시 하위 폴더를 탐색하지 않음",
    )
    return parser


def resolve_input_path(cli_input: str | None) -> Path:
    """CLI 인자가 있으면 우선, 없으면 .env INPUT_DIR을 사용한다."""
    from common.settings import APP_ROOT

    if cli_input:
        path = Path(cli_input)
        return path if path.is_absolute() else APP_ROOT / path

    settings = get_settings()
    return settings.input_dir_path


def main(argv: list[str] | None = None) -> None:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    input_path = resolve_input_path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(
            f"입력 경로를 찾을 수 없습니다: {input_path} "
            f"(.env INPUT_DIR 또는 CLI 인자를 확인하세요)"
        )

    # 기동 시 YAML 검증
    classifier = LabelClassifier.from_yaml()

    if input_path.is_file():
        pdf_files = [input_path]
    else:
        pdf_files = (
            sorted(input_path.glob("*.pdf"))
            if args.non_recursive
            else sorted(input_path.rglob("*.pdf"))
        )

    results: list[dict[str, Any]] = []
    for index, pdf_path in enumerate(pdf_files, start=1):
        result = extract_credit_report(
            pdf_path,
            result_no=index,
            classifier=classifier,
        )
        results.append(result)

    json_path, excel_path, admin_path = commit_batch_outputs(
        results, stem=args.output
    )

    print(json.dumps(
        {
            "json": str(json_path),
            "excel": str(excel_path),
            "admin": str(admin_path),
            "count": len(results),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
