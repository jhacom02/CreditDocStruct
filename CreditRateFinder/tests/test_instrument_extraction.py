from __future__ import annotations

import json
from pathlib import Path

import pytest

from agency.agency import (
    AGENCY_DISPLAY_NAMES,
    detect_agency,
    extract_company_name,
    format_agency_display,
    get_agency_layout,
    is_rating_table_header,
    is_plausible_company_name,
    resolve_agency_key,
)
from classify.undefined_filter import should_include_undefined_record
from common.rating_tokens import find_rating_tokens_in_text, parse_rating_value
from extract.label_fields import decompose_label_fields
from extract.row_rebuild import rebuild_merged_rows
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
from common.models import ExtractedRatingRow, RatingRecord
from common.settings import get_instruments_config, get_settings
from extract.label_fields import decompose_label_fields, split_label_and_issue
from extract.layout import truncate_valid_row_text
from extract.merge import merge_canonical_records, merge_rating_records
from extract.row_parser import parse_rating_row_values
from export.excel import build_excel_row
from export.undefined_store import (
    load_undefined_store,
    make_occurrence_id,
    merge_undefined_occurrences,
    write_undefined_store_tmp,
)
from main import _extract_rows_from_page, commit_batch_outputs, select_and_judge


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


def test_merge_confirms_valid_when_same_rating() -> None:
    primary = _record(
        key="coco_t1",
        status="matched",
        rating="AA",
        outlook="안정적",
        source="pdf_table",
        section="primary_rating",
        evaluation_type="본",
    )
    valid = _record(
        key="coco_t1",
        status="matched",
        rating="AA",
        outlook="안정적",
        source="valid_rating_section",
        section="valid_ratings",
        row_index=1,
    )
    merged, warnings = merge_canonical_records([primary, valid])
    assert len(merged) == 1
    assert merged[0].source == "pdf_table"
    assert merged[0].confirmed_by == ["valid_rating_section"]
    assert warnings == []


def test_merge_keeps_valid_only_instrument() -> None:
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
    merged, _warnings = merge_canonical_records([primary, valid])
    assert {item.instrument_key for item in merged} == {"issuer", "coco_t1"}


def test_merge_conflict_warning() -> None:
    primary = _record(
        key="coco_t1",
        status="matched",
        rating="A+",
        outlook="안정적",
        source="pdf_table",
        section="primary_rating",
        evaluation_type="본",
    )
    valid = _record(
        key="coco_t1",
        status="matched",
        rating="A",
        outlook="안정적",
        source="valid_rating_section",
        section="valid_ratings",
        row_index=1,
    )
    merged, warnings = merge_canonical_records([primary, valid])
    assert len(merged) == 1
    assert merged[0].rating == "A+"
    assert warnings
    assert warnings[0]["code"] == "conflicting_rating_sources"


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
        "result_id": "A0001",
        "company_name": "테스트은행",
        "agency": "NICE신용평가㈜",
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
        "result_id": "A0002",
        "company_name": "테스트은행",
        "agency": "NICE신용평가㈜",
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
        "agency": "NICE신용평가㈜",
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
            "result_id": "A0001",
            "file_name": "a.pdf",
            "file_path": "a.pdf",
            "company_name": "테스트",
            "agency": "NICE신용평가㈜",
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


def test_agency_standard_display_names() -> None:
    assert detect_agency("NICE CREDIT OPINION nice신용평가") == "NICE신용평가㈜"
    assert detect_agency("한국신용평가 KIS") == "한국신용평가㈜"
    assert detect_agency("한국기업평가") == "한국기업평가㈜"
    assert resolve_agency_key("", "NICE_report.pdf") == "nice"
    assert format_agency_display("kr") == "한국기업평가㈜"
    assert set(AGENCY_DISPLAY_NAMES.values()) == {
        "NICE신용평가㈜",
        "한국신용평가㈜",
        "한국기업평가㈜",
    }


def test_company_name_rejects_credit_opinion() -> None:
    assert not is_plausible_company_name("CREDIT OPINION")
    name = extract_company_name(
        "CREDIT OPINION\n평가 개요\n(주)경남은행",
        "경남은행_KR.pdf",
        agency_key="kr",
    )
    assert name != "CREDIT OPINION"
    assert "경남" in name or "CREDIT" not in name.upper()


def test_outlook_parenthetical_and_short_codes() -> None:
    token = parse_rating_value("A+(안정적)")
    assert token is not None
    assert token.rating == "A+"
    assert token.outlook == "안정적"
    assert token.raw_outlook == "(안정적)"

    token_s = parse_rating_value("AA-(S)")
    assert token_s is not None
    assert token_s.outlook == "안정적"
    assert token_s.raw_outlook == "(S)"

    token_stable = parse_rating_value("AA+/Stable")
    assert token_stable is not None
    assert token_stable.outlook == "안정적"
    assert token_stable.raw_outlook in {"Stable", "STABLE"}


def test_rating_false_positives() -> None:
    for text in ("영구A-05", "1A-23", "A-10(사)", "2026-06이"):
        assert find_rating_tokens_in_text(text) == []


def test_nice_label_issue_split_yaml() -> None:
    config = get_instruments_config()
    combined = (
        "조건부자본증권(신종) 경남은행 조건부(상) "
        "2026-06이(신종)영구A-05"
    )
    raw_label, issue_name = split_label_and_issue(combined, config)
    assert raw_label == "조건부자본증권(신종)"
    assert issue_name == (
        "경남은행 조건부(상) 2026-06이(신종)영구A-05"
    )


def test_row_rating_single_any_cell() -> None:
    row = parse_rating_row_values(
        values=["조건부자본증권(신종)", "본", "비고", "A+", "안정적"],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="unit_test",
        header_cells=["평가대상", "종류", "비고", "현재등급", "전망"],
    )
    assert row is not None
    assert row.rating_status == "single"
    assert row.rating == "A+"
    assert row.outlook == "안정적"


def test_label_decompose_coco_issue_bon(classifier: LabelClassifier) -> None:
    header = ["평가대상", "종목", "종류", "현재등급", "전망"]
    row = parse_rating_row_values(
        values=["조건부자본증권(신종)", "제19회", "본", "A+", "안정적"],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="unit_test",
        header_cells=header,
    )
    assert row is not None
    config = get_instruments_config()
    decomposed = decompose_label_fields(
        row, header_cells=header, config=config
    )
    record = classifier.classify_row(decomposed)
    assert record.instrument_key == "coco_t1"
    assert record.evaluation_type == "본"
    assert record.issue_name == "제19회"


def test_kyongnam_bank_primary_success(classifier: LabelClassifier) -> None:
    config = get_instruments_config()
    header = ["평가대상", "종류", "현재등급", "비고"]
    row = parse_rating_row_values(
        values=[
            "CoCo(신종) 조건부(상)2026-06이(신종)영구A-05",
            "본",
            "A+(안정적)",
            "상각형",
        ],
        page_number=1,
        row_index=0,
        section="primary_rating",
        source="pdf_table",
        header_cells=header,
    )
    assert row is not None
    assert row.rating == "A+"
    assert row.outlook == "안정적"
    decomposed = decompose_label_fields(
        row, header_cells=header, config=config
    )
    assert decomposed.raw_label == "CoCo(신종)"
    records, warnings = merge_canonical_records(
        [classifier.classify_row(decomposed)]
    )
    status, fail_reason, selected, _ratings = select_and_judge(records)
    assert status == "success"
    assert fail_reason is None
    assert selected is not None
    assert selected["instrument_key"] == "coco_t1"
    assert selected["evaluation_type"] == "본"
    assert warnings == []


def test_valid_multiple_does_not_fail_selected() -> None:
    primary = _record(
        key="coco_t1",
        status="matched",
        rating="A+",
        outlook="안정적",
        source="pdf_table",
        section="primary_rating",
        evaluation_type="본",
    )
    valid_issuer = _record(
        key="issuer",
        status="matched",
        rating="AA+",
        outlook="안정적",
        source="valid_rating_section",
        section="valid_ratings",
        row_index=1,
    )
    valid_sub = _record(
        key="subordinated",
        status="matched",
        rating="AA-",
        outlook="안정적",
        source="valid_rating_section",
        section="valid_ratings",
        row_index=2,
    )
    merged, _warnings = merge_canonical_records(
        [primary, valid_issuer, valid_sub]
    )
    status, fail_reason, selected, ratings = select_and_judge(merged)
    assert status == "success"
    assert fail_reason is None
    assert selected is not None
    assert selected["instrument_key"] == "coco_t1"
    assert "issuer" in ratings
    assert "subordinated" in ratings


def test_truncate_valid_row_text() -> None:
    noisy = "무보증사채 AA+/Stable BIS자본비율(%) 15"
    trimmed = truncate_valid_row_text(noisy)
    assert "BIS" not in trimmed
    assert "AA+" in trimmed or "Stable" in trimmed


def test_classifier_coco_ifsr_aliases(classifier: LabelClassifier) -> None:
    for label in ("CoCo(신종)", "COCO(신종)", "IFSR"):
        record = classifier.classify_label(label)
        assert record.classification_status == "matched"
        assert record.instrument_key in {"coco_t1", "insurance_payment"}


def test_rebuild_merged_three_products() -> None:
    config = get_instruments_config()
    merged_row = ExtractedRatingRow(
        raw_label="보험금지급능력평가 후순위사채 신종자본증권",
        label_text="보험금지급능력평가 후순위사채 신종자본증권",
        rating_cells=["AAA/안정적"],
        rating_status="single",
        rating="AAA",
        outlook="안정적",
        page=1,
        row_index=0,
        section="primary_rating",
        source="pdf_table",
        cells=[
            "보험금지급능력평가 후순위사채 신종자본증권",
            "본",
            "AAA/안정적",
        ],
        evaluation_type="본",
    )
    rebuilt, error = rebuild_merged_rows([merged_row], config)
    assert error is None
    assert len(rebuilt) == 3
    labels = {item.raw_label for item in rebuilt}
    assert "보험금지급능력평가" in labels
    assert "후순위사채" in labels
    assert "신종자본증권" in labels


def test_rebuild_merged_failure_returns_error() -> None:
    config = get_instruments_config()
    row = ExtractedRatingRow(
        raw_label="본",
        label_text="본",
        rating_cells=[],
        rating_status="none",
        rating=None,
        outlook=None,
        page=1,
        row_index=0,
        section="primary_rating",
        source="pdf_table",
        cells=["본", "정기"],
        evaluation_type="정기",
    )
    rebuilt, error = rebuild_merged_rows([row], config)
    assert rebuilt == []
    assert error == "evaluation_type_only_label"


def test_undefined_filter_excludes_noise() -> None:
    record = _record(
        key=None,
        status="undefined",
        rating="100",
        label="BIS 15.2%",
        rating_status="single",
    )
    assert not should_include_undefined_record(record)

    email_record = _record(
        key=None,
        status="undefined",
        rating="A+",
        label="contact@example.com",
        rating_status="single",
    )
    assert not should_include_undefined_record(email_record)


def test_primary_and_valid_both_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    page = MagicMock()
    primary = ExtractedRatingRow(
        raw_label="신종자본증권",
        rating_cells=["AA"],
        rating_status="single",
        rating="AA",
        outlook=None,
        page=1,
        row_index=0,
        section="primary_rating",
        source="pdf_table",
    )
    valid = ExtractedRatingRow(
        raw_label="BIS",
        rating_cells=["15"],
        rating_status="single",
        rating="15",
        outlook=None,
        page=1,
        row_index=1,
        section="valid_ratings",
        source="valid_rating_section",
    )

    monkeypatch.setattr(
        "main.extract_primary_rows_from_tables",
        lambda **kwargs: [primary],
    )
    monkeypatch.setattr(
        "main.extract_valid_rating_rows",
        lambda **kwargs: [valid],
    )
    monkeypatch.setattr(
        "main.extract_primary_rows_from_visual_layout",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "main.extract_fallback_rows_from_text",
        lambda **kwargs: [],
    )

    rows = _extract_rows_from_page(page, "kis")
    assert len(rows) == 2
    assert rows[0].source == "pdf_table"
    assert rows[1].source == "valid_rating_section"
