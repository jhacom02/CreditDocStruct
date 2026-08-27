"""재무지표 추출·정규화·문서 DB 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from classify.fin_normalize import facts_from_fin_table
from classify.metric_classifier import MetricClassifier
from common.matching_policy import normalize_metric_label
from common.metric_catalog import get_metrics_config
from common.models import ExtractedFinTable
from export.document_store import (
    load_raw_tables,
    renormalize_all,
    upsert_document_result,
)
from extract.fin_tables import (
    align_sparse_period_columns,
    parse_numeric_cell,
    parse_period_header,
    repair_financial_matrix,
    strip_footnote_marker,
    take_first_concatenated_number,
)


def test_parse_period_header_variants() -> None:
    assert parse_period_header("2022.12") == ("2022.12", 2022, 12)
    assert parse_period_header("2021(12)") == ("2021.12", 2021, 12)
    assert parse_period_header("2026.03") == ("2026.03", 2026, 3)
    assert parse_period_header("2021") == ("2021.12", 2021, 12)
    assert parse_period_header("2025") == ("2025.12", 2025, 12)


def test_parse_numeric_cell() -> None:
    assert parse_numeric_cell("48,689")[0] == 48689.0
    assert parse_numeric_cell("n.a.")[0] is None
    assert parse_numeric_cell("-")[0] is None
    assert parse_numeric_cell("(1,200)")[0] == -1200.0


def test_take_first_concatenated_number() -> None:
    assert take_first_concatenated_number("2,111,237 2,348,050") == "2,111,237"
    assert take_first_concatenated_number("849,400 1,247,685") == "849,400"
    assert take_first_concatenated_number("2,549,275") is None
    assert take_first_concatenated_number("매출액 100") is None


def test_align_sparse_period_columns_kis_style() -> None:
    headers = [
        "",
        "",
        "",
        "2022.12",
        "",
        "2023.12",
        "",
        "2024.12",
    ]
    rows = [
        ["매출액(억원)", "", "712,579", "", "882,195", "", "933,989", ""],
        ["자산총계(억원)", "", "2,348,050", "", "2,397,150", "", "2,468,078", ""],
    ]
    out_headers, out_rows = align_sparse_period_columns(headers, rows)
    assert out_headers == ["구분", "2022.12", "2023.12", "2024.12"]
    assert out_rows[0] == ["매출액(억원)", "712,579", "882,195", "933,989"]
    assert out_rows[1][1] == "2,348,050"


def test_repair_financial_matrix_concat_and_sparse() -> None:
    headers = ["구분", "2021.12", "2022.12", "2023.12"]
    rows = [
        ["자산총계", "2,111,237 2,348,050", "2,348,050 2,397,150", "2,397,150"],
    ]
    out_headers, out_rows = repair_financial_matrix(headers, rows)
    assert out_headers == ["구분", "2021.12", "2022.12", "2023.12"]
    assert out_rows[0] == ["자산총계", "2,111,237", "2,348,050", "2,397,150"]


def test_normalize_metric_label_strips_unit_and_footnote() -> None:
    assert normalize_metric_label("총자산(십억원)") == "총자산"
    assert normalize_metric_label("ROA(%)") == "ROA"
    assert normalize_metric_label("NIM(%)주1)") == "NIM"


def test_strip_footnote_marker() -> None:
    label, mark = strip_footnote_marker("총자산주1)")
    assert "총자산" in label
    assert mark is not None


def test_metrics_catalog_eight_keys() -> None:
    config = get_metrics_config()
    assert set(config.metrics) == {
        "total_assets",
        "net_income",
        "total_borrowings",
        "equity",
        "debt_ratio",
        "bis_ratio",
        "liquidity_ratio",
        "leverage",
    }
    assert config.normalized_lookup.get("BIS자본비율") == "bis_ratio"
    assert config.normalized_lookup.get("당기순이익") == "net_income"
    assert "순이익" not in config.normalized_lookup
    assert config.metrics["leverage"].display_name == "총자산/자기자본(배)"


def test_metric_classifier_aliases() -> None:
    classifier = MetricClassifier.from_catalog()
    key, normalized, status = classifier.classify_label("총자산(십억원)")
    assert status == "matched"
    assert key == "total_assets"
    assert normalized == "총자산"
    _, _, undef = classifier.classify_label("지배주주지분순이익")
    assert undef == "undefined"
    key2, _, status2 = classifier.classify_label("차입부채")
    assert status2 == "matched"
    assert key2 == "total_borrowings"


def test_facts_from_fin_table_matched_and_undefined() -> None:
    table = ExtractedFinTable(
        page=1,
        title_raw="주요 재무지표",
        headers=["구분", "2024.12", "2025.12"],
        rows=[
            ["총자산", "1000", "1100"],
            ["알수없는지표XYZ", "1.2", "1.3"],
            ["당기순이익", "10", "11"],
        ],
        basis="별도",
        unit_caption="단위: 십억원, %",
    )
    classifier = MetricClassifier.from_catalog()
    facts, undefined = facts_from_fin_table(table, classifier)
    matched = [f for f in facts if f.classification_status == "matched"]
    assert any(f.metric_key == "total_assets" for f in matched)
    assert any(f.metric_key == "net_income" for f in matched)
    assert any("알수없는지표" in u["raw_label"] for u in undefined)


def test_document_store_roundtrip_and_renormalize(tmp_path: Path) -> None:
    import sqlite3

    from export.document_store import doc_id_from_hash

    db = tmp_path / "documents.db"
    table = ExtractedFinTable(
        page=1,
        title_raw="주요 재무지표",
        headers=["구분", "2024.12"],
        rows=[["자기자본", "500"]],
        source="pdf_table",
    )
    classifier = MetricClassifier.from_catalog()
    facts, _ = facts_from_fin_table(table, classifier)
    file_hash = "abc123def4567890ffffffffffffffffffffffffffffffff"
    result = {
        "file_hash": file_hash,
        "file_name": "sample.pdf",
        "file_path": "sample.pdf",
        "company_name": "테스트은행",
        "agency": "한국신용평가㈜",
        "evaluation_date": "2024-01-01",
        "status": "success",
        "fail_reason": None,
        "products": [
            {
                "instrument_key": "issuer",
                "raw_label": "발행자신용등급",
                "normalized_label": "발행자신용등급",
                "rating": "AAA",
                "outlook": "안정적",
                "evaluation_type": "본",
                "status": "success",
                "fail_reason": None,
                "page": 1,
                "source": "pdf_table",
                "rating_status": "single",
                "section": "primary_rating",
            }
        ],
        "tables": [
            {
                "section_key": "primary_rating",
                "title_raw": "평가개요",
                "page": 1,
                "headers": ["평가대상", "현재등급"],
                "rows": [["발행자신용등급", "AAA"]],
                "region_id": "single",
                "source": "pdf_table",
            }
        ],
        "financial_tables": [table.to_dict()],
        "financial_facts": [f.to_dict() for f in facts],
    }
    upsert_document_result(result, db_path=db)
    doc_id = doc_id_from_hash(file_hash)
    assert doc_id == file_hash[:16]

    loaded = load_raw_tables(file_hash, db_path=db)
    assert len(loaded) == 1
    assert loaded[0].rows[0][0] == "자기자본"

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        doc = conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        assert doc is not None
        assert doc["file_hash"] == file_hash
        assert doc["company_name"] == "테스트은행"

        rating_raw = conn.execute(
            "SELECT * FROM rating_grids_raw WHERE doc_id = ?", (doc_id,)
        ).fetchall()
        assert len(rating_raw) == 1
        assert rating_raw[0]["section_key"] == "primary_rating"

        fin_raw = conn.execute(
            "SELECT * FROM financial_grids_raw WHERE doc_id = ?", (doc_id,)
        ).fetchall()
        assert len(fin_raw) == 1

        rating_rows = conn.execute(
            "SELECT * FROM rating_norm WHERE doc_id = ?", (doc_id,)
        ).fetchall()
        assert len(rating_rows) == 1
        assert rating_rows[0]["instrument_key"] == "issuer"
        assert rating_rows[0]["rating"] == "AAA"

        fin_rows = conn.execute(
            "SELECT * FROM financial_norm WHERE doc_id = ?", (doc_id,)
        ).fetchall()
        assert len(fin_rows) >= 1

    stats = renormalize_all(db_path=db, classifier=classifier)
    assert stats["documents"] == 1
    assert stats["facts"] >= 1
