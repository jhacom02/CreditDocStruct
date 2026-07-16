from __future__ import annotations

import json
from pathlib import Path

import pytest

from credit_scanner.agency import get_agency_layout, is_rating_table_header
from credit_scanner.classifier import InstrumentClassifier
from credit_scanner.export.review import (
    build_review_rows,
    suggest_taxonomy_aliases,
)
from credit_scanner.extract.row_parser import parse_rating_row_values
from credit_scanner.pipeline import collect_review_records


FIXTURES = Path(__file__).parent / "fixtures"
TAXONOMY = (
    Path(__file__).resolve().parents[1]
    / "credit_scanner"
    / "config"
    / "instrument_taxonomy.yaml"
)


@pytest.fixture(scope="module")
def classifier() -> InstrumentClassifier:
    return InstrumentClassifier.from_yaml(TAXONOMY)


def test_label_variants_across_agencies(classifier: InstrumentClassifier) -> None:
    cases = json.loads(
        (FIXTURES / "label_variants.json").read_text(encoding="utf-8")
    )

    failures: list[str] = []

    for case in cases:
        result = classifier.classify(case["label"])
        expected = case["expected"]

        if expected == "unknown":
            if result.status != "unknown":
                failures.append(
                    f"{case['label']!r} expected unknown, got "
                    f"{result.instrument_type}/{result.status}"
                )
            continue

        if result.status != "matched" or result.instrument_type != expected:
            failures.append(
                f"{case['label']!r} ({case['agency']}) expected {expected}, "
                f"got {result.instrument_type}/{result.status} "
                f"score={result.score} features={result.features}"
            )

    assert not failures, "\n".join(failures)


def test_coco_t2_preferred_over_plain_subordinated(
    classifier: InstrumentClassifier,
) -> None:
    result = classifier.classify("조건부자본증권(후순위)")
    assert result.status == "matched"
    assert result.instrument_type == "coco_t2"


def test_issuer_발행자_wording(classifier: InstrumentClassifier) -> None:
    for label in ("발행자", "발행자 신용등급", "발행자신용등급"):
        result = classifier.classify(label)
        assert result.instrument_type == "issuer"
        assert result.status == "matched"


def test_unknown_row_preserved_with_rating(
    classifier: InstrumentClassifier,
) -> None:
    record = parse_rating_row_values(
        values=["신규형특수채권상품XYZ", "본평가", "AA+", "유지"],
        agency="NICE신용평가",
        file_name="sample.pdf",
        page_number=1,
        section="primary_rating",
        source="unit_test",
        confidence=0.99,
        classifier=classifier,
    )

    assert record is not None
    assert record.current_rating == "AA+"
    assert record.instrument_type == "unknown"
    assert record.classification_status == "unknown"
    assert "신규형특수채권상품XYZ" in record.raw_label


def test_known_row_still_classified(
    classifier: InstrumentClassifier,
) -> None:
    record = parse_rating_row_values(
        values=["발행자 신용등급", "본평가", "AAA/Stable", "AA+/Stable", "상향"],
        agency="한국신용평가",
        file_name="sample.pdf",
        page_number=1,
        section="primary_rating",
        source="unit_test",
        confidence=0.99,
        classifier=classifier,
    )

    assert record is not None
    assert record.instrument_type == "issuer"
    assert record.classification_status == "matched"
    assert record.current_rating == "AAA"
    assert record.current_outlook == "Stable"
    assert record.rating_action == "상향"


def test_agency_layout_headers() -> None:
    nice = get_agency_layout("NICE신용평가")
    kis = get_agency_layout("한국신용평가")
    kr = get_agency_layout("한국기업평가")

    assert is_rating_table_header("평가대상현재등급직전등급", nice)
    assert is_rating_table_header("구분현재등급ratingaction", kis)
    assert is_rating_table_header("종목현재등급", kr)
    assert not is_rating_table_header("회사개요주요재무", nice)

    assert any("Credit" in p for p in nice.primary_section_patterns)
    assert any("등급" in p for p in kis.primary_end_patterns)
    assert kr.valid_rating_max_width >= 360


def test_review_sheet_and_alias_suggestions(
    classifier: InstrumentClassifier,
) -> None:
    unknown = parse_rating_row_values(
        values=["미등록상품알파", "본평가", "A+"],
        agency="한국기업평가",
        file_name="a.pdf",
        page_number=1,
        section="primary_rating",
        source="unit_test",
        confidence=0.9,
        classifier=classifier,
    )
    assert unknown is not None

    result = {
        "file_name": "a.pdf",
        "agency": "한국기업평가",
        "review_records": [unknown.__dict__],
    }

    review_rows = build_review_rows([result])
    assert len(review_rows) == 1
    assert review_rows[0]["분류상태"] == "unknown"

    review_rows[0]["제안_canonical_type"] = "senior_unsecured"
    snippets = suggest_taxonomy_aliases(review_rows)
    assert any("senior_unsecured" in line for line in snippets)
    assert any("미등록상품알파" in line for line in snippets)


def test_collect_review_records(classifier: InstrumentClassifier) -> None:
    matched = parse_rating_row_values(
        values=["무보증사채", "정기", "AA"],
        agency="NICE신용평가",
        file_name="b.pdf",
        page_number=1,
        section="primary_rating",
        source="unit_test",
        confidence=0.9,
        classifier=classifier,
    )
    unknown = parse_rating_row_values(
        values=["이상한상품", "정기", "A"],
        agency="NICE신용평가",
        file_name="b.pdf",
        page_number=1,
        section="primary_rating",
        source="unit_test",
        confidence=0.9,
        classifier=classifier,
    )

    assert matched is not None and unknown is not None
    review = collect_review_records([matched, unknown])
    assert len(review) == 1
    assert review[0].instrument_type == "unknown"
