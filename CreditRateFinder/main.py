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
    MULTIPLE_INSTRUMENTS,
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
from common.settings import get_instruments_config, get_settings
from extract import (
    extract_fallback_rows_from_text,
    extract_primary_rows_from_tables,
    extract_primary_rows_from_visual_layout,
    extract_valid_rating_rows,
)
from extract.row_rebuild import rebuild_merged_rows
from extract.row_parser import PRIMARY_EVAL_TYPES
from extract.merge import is_primary_record, merge_canonical_records
from export.excel import write_results_excel_tmp
from export.json_io import write_results_json_tmp
from export.undefined_store import (
    file_sha256,
    load_undefined_store,
    make_occurrence_id,
    merge_undefined_occurrences,
    write_undefined_store_tmp,
)

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


def _selected_dict(record: RatingRecord) -> dict[str, Any]:
    return {
        "raw_label": record.raw_label,
        "normalized_label": record.normalized_label,
        "instrument_key": record.instrument_key,
        "classification_status": record.classification_status,
        "rating": record.rating,
        "outlook": record.outlook,
        "rating_status": record.rating_status,
        "page": record.page,
        "row_index": record.row_index,
        "section": record.section,
        "source": record.source,
        "evaluation_type": record.evaluation_type,
    }


def _build_ratings_sparse(
    rating_groups: dict[str, list[RatingRecord]],
) -> dict[str, Any]:
    ratings: dict[str, Any] = {}
    for key, group in rating_groups.items():
        if any(item.rating_status == "ambiguous" for item in group):
            ratings[key] = None
            continue
        distinct = {(item.rating, item.outlook) for item in group}
        if len(distinct) != 1:
            ratings[key] = None
        else:
            chosen = group[0]
            ratings[key] = {
                "rating": chosen.rating,
                "outlook": chosen.outlook,
                "page": chosen.page,
            }
    return ratings


def select_and_judge(
    records: list[RatingRecord],
) -> tuple[str, dict[str, str] | None, dict[str, Any] | None, dict[str, Any]]:
    """선택 알고리즘 + fail_reason 판정.

    Returns:
        status, fail_reason, selected_dict, ratings_sparse
    """
    matched = [
        record
        for record in records
        if record.classification_status == "matched"
    ]
    primary_matched = [
        record for record in matched if is_primary_record(record)
    ]

    # ratings sparse: canonical 전체 (valid-only 상품 포함)
    groups: dict[str, list[RatingRecord]] = defaultdict(list)
    for record in matched:
        if record.instrument_key and record.rating_status in {
            "single",
            "ambiguous",
        }:
            groups[record.instrument_key].append(record)

    rating_groups = dict(groups)
    ratings = _build_ratings_sparse(rating_groups)

    # selected: Primary만
    bon_candidates = [
        record
        for record in primary_matched
        if record.evaluation_type in PRIMARY_EVAL_TYPES
        and record.rating_status == "single"
        and record.instrument_key
        and record.rating
    ]
    if bon_candidates:
        bon_keys = {record.instrument_key for record in bon_candidates}
        if len(bon_keys) >= 2:
            return (
                "fail",
                make_fail_reason(MULTIPLE_INSTRUMENTS),
                None,
                ratings,
            )
        if len(bon_candidates) >= 2 and len(bon_keys) == 1:
            distinct = {
                (item.rating, item.outlook) for item in bon_candidates
            }
            if len(distinct) >= 2:
                return (
                    "fail",
                    make_fail_reason(MULTIPLE_RATINGS),
                    None,
                    ratings,
                )
        chosen = bon_candidates[0]
        return "success", None, _selected_dict(chosen), ratings

    primary_groups: dict[str, list[RatingRecord]] = defaultdict(list)
    for record in primary_matched:
        if record.instrument_key and record.rating_status in {
            "single",
            "ambiguous",
        }:
            primary_groups[record.instrument_key].append(record)

    primary_rating_groups = dict(primary_groups)

    if len(primary_rating_groups) >= 2:
        return "fail", make_fail_reason(MULTIPLE_INSTRUMENTS), None, ratings

    if len(primary_rating_groups) == 1:
        _instrument_key, group = next(iter(primary_rating_groups.items()))
        if any(item.rating_status == "ambiguous" for item in group):
            return (
                "fail",
                make_fail_reason(MULTIPLE_RATING_COLUMNS),
                None,
                ratings,
            )

        distinct = {(item.rating, item.outlook) for item in group}
        if len(distinct) >= 2:
            return "fail", make_fail_reason(MULTIPLE_RATINGS), None, ratings

        chosen = group[0]
        return "success", None, _selected_dict(chosen), ratings

    if primary_matched:
        return "fail", make_fail_reason(RATING_NOT_FOUND), None, ratings

    if matched:
        return "fail", make_fail_reason(RATING_NOT_FOUND), None, ratings

    rated_rows = [
        record
        for record in records
        if record.rating_status in {"single", "ambiguous"}
        or record.rating
    ]
    if rated_rows:
        label_missing = any(
            not (record.raw_label or "").strip()
            or record.normalized_label == ""
            for record in rated_rows
        )
        if label_missing:
            return "fail", make_fail_reason(LABEL_NOT_FOUND), None, ratings

        if any(
            record.classification_status == "undefined"
            for record in rated_rows
        ):
            return "fail", make_fail_reason(UNDEFINED_LABEL), None, ratings

        return "fail", make_fail_reason(LABEL_NOT_FOUND), None, ratings

    return "fail", make_fail_reason(PARSE_ERROR), None, ratings


def _extract_rows_from_page(
    page: pymupdf.Page,
    agency_key: str,
) -> list[ExtractedRatingRow]:
    table_rows = extract_primary_rows_from_tables(page=page, agency=agency_key)
    if table_rows:
        primary_rows = table_rows
    else:
        primary_rows = extract_primary_rows_from_visual_layout(
            page=page, agency=agency_key
        )

    valid_rows = extract_valid_rating_rows(page=page, agency=agency_key)
    rows = list(primary_rows) + list(valid_rows)

    if not primary_rows and not valid_rows:
        rows.extend(extract_fallback_rows_from_text(page=page))

    return rows


def extract_credit_report(
    pdf_path: str | Path,
    *,
    result_id: str | None = None,
    classifier: LabelClassifier | None = None,
) -> dict[str, Any]:
    """단일 PDF를 처리해 결과 객체를 반환한다."""
    settings = get_settings()
    pdf_path = Path(pdf_path)
    active = classifier or LabelClassifier.from_yaml()

    if not pdf_path.exists():
        return {
            "result_id": result_id,
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "company_name": pdf_path.stem,
            "agency": format_agency_display(None),
            "status": "fail",
            "fail_reason": make_fail_reason(FILE_ERROR),
            "selected": None,
            "ratings": {},
            "records": [],
            "undefined_records": [],
            "validation_warnings": [],
            "extracted_text_chars": 0,
            "extracted_word_count": 0,
            "rating_token_count": 0,
            "file_hash": None,
        }

    try:
        file_hash = file_sha256(pdf_path)
        document = pymupdf.open(pdf_path)
    except Exception:
        return {
            "result_id": result_id,
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "company_name": pdf_path.stem,
            "agency": format_agency_display(None),
            "status": "fail",
            "fail_reason": make_fail_reason(FILE_ERROR),
            "selected": None,
            "ratings": {},
            "records": [],
            "undefined_records": [],
            "validation_warnings": [],
            "extracted_text_chars": 0,
            "extracted_word_count": 0,
            "rating_token_count": 0,
            "file_hash": None,
        }

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
            return {
                "result_id": result_id,
                "file_name": pdf_path.name,
                "file_path": str(pdf_path),
                "company_name": company_name,
                "agency": agency,
                "status": "fail",
                "fail_reason": make_fail_reason(PARSE_ERROR),
                "selected": None,
                "ratings": {},
                "records": [],
                "undefined_records": [],
            "validation_warnings": [],
                "extracted_text_chars": extracted_text_chars,
                "extracted_word_count": extracted_word_count,
                "rating_token_count": rating_token_count,
                "file_hash": file_hash,
            }

        if not rebuilt_rows:
            if (
                extracted_text_chars < settings.min_extracted_text_chars
                and rating_token_count == 0
            ):
                fail_code = TEXT_EXTRACTION_FAILED
            else:
                fail_code = PARSE_ERROR
            return {
                "result_id": result_id,
                "file_name": pdf_path.name,
                "file_path": str(pdf_path),
                "company_name": company_name,
                "agency": agency,
                "status": "fail",
                "fail_reason": make_fail_reason(fail_code),
                "selected": None,
                "ratings": {},
                "records": [],
                "undefined_records": [],
            "validation_warnings": [],
                "extracted_text_chars": extracted_text_chars,
                "extracted_word_count": extracted_word_count,
                "rating_token_count": rating_token_count,
                "file_hash": file_hash,
            }

        records, validation_warnings = merge_canonical_records(
            _dedupe_records(active.classify_rows(rebuilt_rows))
        )
        status, fail_reason, selected, ratings = select_and_judge(records)

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
            "result_id": result_id,
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "company_name": company_name,
            "agency": agency,
            "status": status,
            "fail_reason": fail_reason,
            "selected": selected,
            "ratings": ratings,
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
    settings = get_settings()
    if override:
        return override
    today = date.today().strftime("%Y%m%d")
    return f"{settings.result_filename_prefix}_{today}"


def _format_result_id(index: int) -> str:
    """JSON/Excel 표시용 결과 ID (고정 형식 A0001)."""
    return f"A{index:04d}"


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
                    "agency": result.get("agency"),
                    "rating": record.get("rating"),
                    "suggestions": record.get("suggestions") or [],
                }
            )
    return occurrences


def commit_batch_outputs(
    results: list[dict[str, Any]],
    *,
    stem: str | None = None,
) -> tuple[Path, Path, Path]:
    """JSON·Excel·admin/undefined.json을 임시 파일로 쓴 뒤 원자적 교체."""
    settings = get_settings()
    config = get_instruments_config()

    result_stem = _result_stem(stem)
    result_dir = settings.result_dir_path
    result_dir.mkdir(parents=True, exist_ok=True)

    json_final = result_dir / f"{result_stem}.json"
    excel_final = result_dir / f"{result_stem}.xlsx"
    admin_final = settings.undefined_json_path

    json_tmp = write_results_json_tmp(results, json_final)
    excel_tmp = write_results_excel_tmp(results, config, excel_final)

    store = load_undefined_store(admin_final)
    merged = merge_undefined_occurrences(
        store, collect_undefined_occurrences(results)
    )
    admin_tmp = write_undefined_store_tmp(merged, admin_final)

    # 모든 tmp 쓰기 성공 후 원자적 교체
    try:
        os.replace(json_tmp, json_final)
        os.replace(excel_tmp, excel_final)
        os.replace(admin_tmp, admin_final)
    except Exception:
        # 부분 교체 실패 시 남은 tmp 정리 시도
        for tmp in (json_tmp, excel_tmp, admin_tmp):
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
        raise

    return json_final, excel_final, admin_final


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
            result_id=_format_result_id(index),
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
