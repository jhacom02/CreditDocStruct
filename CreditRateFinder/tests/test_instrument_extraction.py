from __future__ import annotations

import json
from pathlib import Path

import pytest

from agency.agency import get_agency_layout, is_rating_table_header
from classify.classifier import LabelClassifier
from common.fail_reasons import (
    MULTIPLE_INSTRUMENTS,
    MULTIPLE_RATING_COLUMNS,
    MULTIPLE_RATINGS,
    RATING_NOT_FOUND,
    TEXT_EXTRACTION_FAILED,
    UNDEFINED_LABEL,
    PRIORITY_ORDER,
)
from common.models import RatingRecord
from common.settings import get_instruments_config, get_settings
from extract.merge import merge_rating_records
from extract.row_parser import parse_rating_row_values
from export.excel import build_excel_row
from export.undefined_store import (
    load_undefined_store,
    make_occurrence_id,
    merge_undefined_occurrences,
    write_undefined_store_tmp,
)
from main import commit_batch_outputs, select_and_judge


@pytest.fixture(scope="module")
def classifier() -> LabelClassifier:
    return LabelClassifier.from_yaml()


def test_label_variants_exact_match(classifier: LabelClassifier) -> None:
    cases = json.loads(
        (Path(__file__).parent / "label_variants.json").read_text(
            encoding="utf-8"
        )
    )

    failures: list[str] = []
    for case in cases:
        result = classifier.classify_label(case["label"])
        expected = case["expected"]

        if expected == "undefined":
            if result.classification_status != "undefined":
                failures.append(
                    f"{case['label']!r} expected undefined, got "
                    f"{result.instrument_key}/{result.classification_status}"
                )
            elif not result.suggestions:
                failures.append(
                    f"{case['label']!r} undefined but suggestions empty"
                )
            elif result.instrument_key is not None:
                failures.append(
                    f"{case['label']!r} undefined but key auto-set"
                )
            continue

        if (
            result.classification_status != "matched"
            or result.instrument_key != expected
        ):
            failures.append(
                f"{case['label']!r} expected {expected}, "
                f"got {result.instrument_key}/{result.classification_status}"
            )

    assert not failures, "\n".join(failures)


def test_row_parser_rating_status_single() -> None:
    row = parse_rating_row_values(
        values=["조건부자본증권(신종)", "본평가", "A+", "안정적"],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="unit_test",
    )
    assert row is not None
    assert row.rating_status == "single"
    assert row.rating == "A+"
    assert row.outlook == "안정적"
    assert row.evaluation_type == "본평가"


def test_row_parser_current_equals_previous_with_header() -> None:
    header = ["평가대상", "종류", "현재등급", "직전등급", "Rating Action"]
    row = parse_rating_row_values(
        values=["보험금지급능력평가", "본", "AAA/안정적", "AAA/안정적", "유지"],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="pdf_table",
        header_cells=header,
    )
    assert row is not None
    assert row.rating_status == "single"
    assert row.rating == "AAA"
    assert row.outlook == "안정적"
    assert row.evaluation_type == "본"


def test_row_parser_current_differs_from_previous_with_header() -> None:
    header = ["평가대상", "종류", "현재등급", "직전등급", "Rating Action"]
    row = parse_rating_row_values(
        values=["후순위사채", "정기", "AA+/안정적", "AA/안정적", "유지"],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="pdf_table",
        header_cells=header,
    )
    assert row is not None
    assert row.rating_status == "single"
    assert row.rating == "AA+"
    assert row.outlook == "안정적"
    assert row.evaluation_type == "정기"


def test_row_parser_multiple_rating_cells_ambiguous_without_header() -> None:
    row = parse_rating_row_values(
        values=["조건부자본증권(신종)", "A", "A+"],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="unit_test",
    )
    assert row is not None
    assert row.rating_status == "ambiguous"
    assert row.rating is None


def test_row_parser_duplicate_same_rating_two_cells_ambiguous_without_header() -> None:
    row = parse_rating_row_values(
        values=["조건부자본증권(신종)", "AA+", "AA+", "안정적"],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="unit_test",
    )
    assert row is not None
    assert row.rating_status == "ambiguous"


def test_row_parser_current_cell_multi_token_ambiguous() -> None:
    header = ["평가대상", "종류", "현재등급", "직전등급"]
    row = parse_rating_row_values(
        values=["신종자본증권", "본", "AA+ AA-", "AA/안정적"],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="pdf_table",
        header_cells=header,
    )
    assert row is not None
    assert row.rating_status == "ambiguous"
    assert row.rating is None


def test_classifier_does_not_recompute_rating(
    classifier: LabelClassifier,
) -> None:
    row = parse_rating_row_values(
        values=["신종자본증권", "AA+"],
        page_number=1,
        row_index=3,
        section="primary_rating",
        source="unit_test",
    )
    assert row is not None
    record = classifier.classify_row(row)
    assert record.classification_status == "matched"
    assert record.instrument_key == "coco_t1"
    assert record.rating == row.rating
    assert record.rating_status == row.rating_status
    assert record.evaluation_type == row.evaluation_type


def _record(
    *,
    key: str | None,
    status: str,
    rating: str | None,
    outlook: str | None = None,
    rating_status: str = "single",
    label: str = "label",
    page: int = 1,
    row_index: int = 0,
    evaluation_type: str | None = None,
    source: str = "pdf_table",
    section: str = "primary_rating",
) -> RatingRecord:
    return RatingRecord(
        raw_label=label,
        normalized_label=label.replace(" ", ""),
        instrument_key=key,
        classification_status=status,  # type: ignore[arg-type]
        rating=rating,
        outlook=outlook,
        rating_status=rating_status,  # type: ignore[arg-type]
        page=page,
        row_index=row_index,
        evaluation_type=evaluation_type,
        source=source,
        section=section,
    )


def test_select_success_single_candidate() -> None:
    status, fail_reason, selected, ratings = select_and_judge(
        [
            _record(key="coco_t1", status="matched", rating="A+"),
            _record(
                key=None,
                status="undefined",
                rating="AA",
                label="미등록상품",
            ),
        ]
    )
    assert status == "success"
    assert fail_reason is None
    assert selected is not None
    assert selected["instrument_key"] == "coco_t1"
    assert "coco_t1" in ratings


def test_select_multiple_instruments() -> None:
    status, fail_reason, selected, _ = select_and_judge(
        [
            _record(key="coco_t1", status="matched", rating="A+"),
            _record(key="issuer", status="matched", rating="AAA"),
        ]
    )
    assert status == "fail"
    assert fail_reason is not None
    assert fail_reason["code"] == MULTIPLE_INSTRUMENTS
    assert selected is None


def test_select_bon_over_regular() -> None:
    status, fail_reason, selected, ratings = select_and_judge(
        [
            _record(
                key="insurance_payment",
                status="matched",
                rating="AAA",
                outlook="안정적",
                label="보험금지급능력평가",
                evaluation_type="본",
            ),
            _record(
                key="subordinated",
                status="matched",
                rating="AA+",
                outlook="안정적",
                label="후순위사채",
                evaluation_type="정기",
                row_index=1,
            ),
            _record(
                key="coco_t1",
                status="matched",
                rating="AA",
                outlook="안정적",
                label="신종자본증권",
                evaluation_type="정기",
                row_index=2,
            ),
        ]
    )
    assert status == "success"
    assert fail_reason is None
    assert selected is not None
    assert selected["instrument_key"] == "insurance_payment"
    assert selected["evaluation_type"] == "본"
    assert set(ratings) == {"insurance_payment", "subordinated", "coco_t1"}


def test_select_multiple_bon_instruments() -> None:
    status, fail_reason, selected, _ = select_and_judge(
        [
            _record(
                key="insurance_payment",
                status="matched",
                rating="AAA",
                evaluation_type="본",
            ),
            _record(
                key="coco_t1",
                status="matched",
                rating="AA",
                evaluation_type="본",
                row_index=1,
            ),
        ]
    )
    assert status == "fail"
    assert fail_reason is not None
    assert fail_reason["code"] == MULTIPLE_INSTRUMENTS
    assert selected is None


def test_select_multiple_rating_columns() -> None:
    status, fail_reason, selected, _ = select_and_judge(
        [
            _record(
                key="coco_t1",
                status="matched",
                rating=None,
                rating_status="ambiguous",
            )
        ]
    )
    assert status == "fail"
    assert fail_reason is not None
    assert fail_reason["code"] == MULTIPLE_RATING_COLUMNS
    assert selected is None


def test_select_multiple_ratings() -> None:
    status, fail_reason, selected, _ = select_and_judge(
        [
            _record(key="coco_t1", status="matched", rating="A+"),
            _record(
                key="coco_t1",
                status="matched",
                rating="AA",
                row_index=1,
            ),
        ]
    )
    assert status == "fail"
    assert fail_reason is not None
    assert fail_reason["code"] == MULTIPLE_RATINGS
    assert selected is None


def test_select_rating_not_found() -> None:
    status, fail_reason, selected, _ = select_and_judge(
        [
            _record(
                key="coco_t1",
                status="matched",
                rating=None,
                rating_status="none",
            )
        ]
    )
    assert status == "fail"
    assert fail_reason is not None
    assert fail_reason["code"] == RATING_NOT_FOUND
    assert selected is None


def test_select_undefined_label() -> None:
    status, fail_reason, selected, _ = select_and_judge(
        [
            _record(
                key=None,
                status="undefined",
                rating="A+",
                label="미등록상품XYZ",
            )
        ]
    )
    assert status == "fail"
    assert fail_reason is not None
    assert fail_reason["code"] == UNDEFINED_LABEL
    assert selected is None


def test_merge_drops_valid_when_primary_has_instrument() -> None:
    primary = _record(
        key="coco_t1",
        status="matched",
        rating="AA",
        source="pdf_table",
        section="primary_rating",
        evaluation_type="본",
    )
    valid = _record(
        key="coco_t1",
        status="matched",
        rating="AA",
        source="valid_rating_section",
        section="valid_ratings",
        row_index=1,
    )
    visual = _record(
        key="coco_t1",
        status="matched",
        rating="AA-",
        source="visual_layout",
        section="primary_rating",
        row_index=2,
    )
    merged = merge_rating_records([primary, valid, visual])
    assert len(merged) == 1
    assert merged[0].source == "pdf_table"
    assert merged[0].rating == "AA"


def test_merge_keeps_valid_when_primary_missing_instrument() -> None:
    primary = _record(
        key="issuer",
        status="matched",
        rating="AAA",
        source="pdf_table",
        section="primary_rating",
    )
    valid = _record(
        key="coco_t1",
        status="matched",
        rating="AA",
        source="valid_rating_section",
        section="valid_ratings",
        row_index=1,
    )
    merged = merge_rating_records([primary, valid])
    assert {item.instrument_key for item in merged} == {"issuer", "coco_t1"}


def test_fail_reason_priority_has_text_extraction_failed() -> None:
    assert TEXT_EXTRACTION_FAILED in PRIORITY_ORDER
    assert "ocr_required" not in PRIORITY_ORDER
    assert PRIORITY_ORDER[1] == TEXT_EXTRACTION_FAILED


def test_min_extracted_text_chars_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from common import settings as settings_mod

    monkeypatch.setenv("MIN_EXTRACTED_TEXT_CHARS", "77")
    settings_mod.get_settings.cache_clear()
    assert get_settings().min_extracted_text_chars == 77
    settings_mod.get_settings.cache_clear()


def test_agency_layout_headers() -> None:
    nice = get_agency_layout("NICE신용평가")
    kis = get_agency_layout("한국신용평가")
    kr = get_agency_layout("한국기업평가")

    assert is_rating_table_header("평가대상현재등급직전등급", nice)
    assert is_rating_table_header("구분현재등급ratingaction", kis)
    assert is_rating_table_header("종목현재등급", kr)
    assert not is_rating_table_header("회사개요주요재무", nice)


def test_excel_row_uses_selected() -> None:
    config = get_instruments_config()
    result = {
        "result_id": "R000001",
        "company_name": "테스트은행",
        "agency": "NICE신용평가",
        "status": "success",
        "file_name": "a.pdf",
        "selected": {
            "instrument_key": "coco_t1",
            "raw_label": "신종자본증권",
            "rating": "A+",
            "outlook": "안정적",
        },
    }
    row = build_excel_row(result, config)
    assert row["대분류_Key"] == "coco_t1"
    assert row["대분류명"] == config.instruments["coco_t1"].major_category_name
    assert row["소분류_원본라벨"] == "신종자본증권"
    assert row["신용등급"] == "A+"


def test_excel_fail_blanks_fields() -> None:
    config = get_instruments_config()
    result = {
        "result_id": "R000002",
        "company_name": "테스트은행",
        "agency": "NICE신용평가",
        "status": "fail",
        "file_name": "b.pdf",
        "selected": None,
    }
    row = build_excel_row(result, config)
    assert row["대분류_Key"] == ""
    assert row["신용등급"] == ""


def test_undefined_occurrence_dedup(tmp_path: Path) -> None:
    store = {"schema_version": 1, "updated_at": None, "entries": []}
    occurrence_id = make_occurrence_id("abc123", "미등록상품", 1, 0)
    occurrence = {
        "occurrence_id": occurrence_id,
        "normalized_label": "미등록상품",
        "raw_label": "미등록상품",
        "file_name": "a.pdf",
        "agency": "NICE신용평가",
        "rating": "A+",
        "suggestions": [],
    }

    merged1 = merge_undefined_occurrences(store, [occurrence])
    assert merged1["entries"][0]["occurrence_count"] == 1

    merged2 = merge_undefined_occurrences(merged1, [occurrence])
    assert merged2["entries"][0]["occurrence_count"] == 1
    assert len(merged2["entries"][0]["occurrence_ids"]) == 1

    occurrence2 = dict(occurrence)
    occurrence2["occurrence_id"] = make_occurrence_id(
        "def456", "미등록상품", 1, 0
    )
    merged3 = merge_undefined_occurrences(merged2, [occurrence2])
    assert merged3["entries"][0]["occurrence_count"] == 2

    admin_path = tmp_path / "undefined.json"
    tmp = write_undefined_store_tmp(merged3, admin_path)
    assert tmp.exists()
    tmp.replace(admin_path)
    loaded = load_undefined_store(admin_path)
    assert loaded["entries"][0]["occurrence_count"] == 2


def test_commit_batch_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from common import settings as settings_mod

    monkeypatch.setenv("RESULT_DIR", str(tmp_path / "result"))
    monkeypatch.setenv("ADMIN_DIR", str(tmp_path / "admin"))
    settings_mod.get_settings.cache_clear()

    settings = settings_mod.get_settings()
    settings.result_dir_path.mkdir(parents=True, exist_ok=True)
    settings.admin_dir_path.mkdir(parents=True, exist_ok=True)
    (settings.admin_dir_path / "undefined.json").write_text(
        '{"schema_version":1,"updated_at":null,"entries":[]}',
        encoding="utf-8",
    )

    results = [
        {
            "result_id": "R000001",
            "file_name": "a.pdf",
            "file_path": "a.pdf",
            "company_name": "테스트",
            "agency": "NICE신용평가",
            "status": "success",
            "fail_reason": None,
            "selected": {
                "instrument_key": "coco_t1",
                "raw_label": "신종자본증권",
                "rating": "A+",
                "outlook": None,
            },
            "ratings": {
                "coco_t1": {"rating": "A+", "outlook": None, "page": 1}
            },
            "records": [],
            "undefined_records": [],
            "file_hash": "abc",
        }
    ]

    json_path, excel_path, admin_path = commit_batch_outputs(
        results, stem="result_test"
    )
    assert json_path.exists()
    assert excel_path.exists()
    assert admin_path.exists()
    assert not json_path.with_name(json_path.name + ".tmp").exists()

    settings_mod.get_settings.cache_clear()
