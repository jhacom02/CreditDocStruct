"""PDF 문서·등급/재무 raw·정규화 결과 SQLite 저장소.

테이블:
  documents           — PDF 요약
  rating_grids_raw    — 신용등급 섹션 그리드 원본
  financial_grids_raw — 재무지표 섹션 그리드 원본
  rating_norm         — 상품별 신용등급 추출 결과
  financial_norm      — 재무지표 추출 결과

API 결과 dict의 financial_facts / products 키는 호환용으로 유지하고,
DB 테이블명만 *_norm / *_grids_raw 를 쓴다.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from classify.fin_normalize import facts_from_fin_tables
from classify.metric_classifier import MetricClassifier
from common.models import ExtractedFinTable, FinancialFact
from common.settings import get_settings
from extract.section_catalog import SECTION_FINANCIAL, SECTION_PRIMARY, SECTION_VALID

KST = ZoneInfo("Asia/Seoul")

_RATING_SECTION_KEYS = frozenset({SECTION_PRIMARY, SECTION_VALID})
DOC_ID_HEX_LEN = 16


def doc_id_from_hash(file_hash: str) -> str:
    """SHA-256 hex의 앞 16자로 문서 id를 만든다."""
    return str(file_hash)[:DOC_ID_HEX_LEN]


def _now_iso() -> str:
    return datetime.now(tz=KST).isoformat(timespec="seconds")


def _db_path(db_path: Path | None = None) -> Path:
    if db_path is not None:
        return db_path
    return get_settings().document_db_path_resolved


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_document_db(db_path: Path | None = None) -> Path:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id              TEXT PRIMARY KEY,
                file_hash           TEXT NOT NULL UNIQUE,
                file_name           TEXT,
                file_path           TEXT,
                company_name        TEXT,
                agency              TEXT,
                evaluation_date     TEXT,
                status              TEXT,
                fail_reason_json    TEXT,
                processed_at        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rating_grids_raw (
                doc_id          TEXT NOT NULL,
                row_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                section_key     TEXT NOT NULL,
                table_index     INTEGER NOT NULL,
                page            INTEGER,
                title_raw       TEXT,
                region_id       TEXT,
                source          TEXT,
                headers_json    TEXT NOT NULL,
                rows_json       TEXT NOT NULL,
                bbox_json       TEXT,
                UNIQUE(doc_id, section_key, table_index),
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            );

            CREATE TABLE IF NOT EXISTS financial_grids_raw (
                doc_id          TEXT NOT NULL,
                row_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                table_index     INTEGER NOT NULL,
                page            INTEGER,
                title_raw       TEXT,
                source          TEXT,
                basis           TEXT,
                unit_caption    TEXT,
                footnotes_json  TEXT,
                headers_json    TEXT NOT NULL,
                rows_json       TEXT NOT NULL,
                bbox_json       TEXT,
                UNIQUE(doc_id, table_index),
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            );

            CREATE TABLE IF NOT EXISTS rating_norm (
                doc_id              TEXT NOT NULL,
                row_id              INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_key      TEXT,
                raw_label           TEXT,
                normalized_label    TEXT,
                rating              TEXT,
                outlook             TEXT,
                evaluation_type     TEXT,
                status              TEXT,
                fail_reason_json    TEXT,
                page                INTEGER,
                source              TEXT,
                rating_status       TEXT,
                section             TEXT,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            );
            CREATE INDEX IF NOT EXISTS idx_rating_norm_doc
                ON rating_norm(doc_id);
            CREATE INDEX IF NOT EXISTS idx_rating_norm_key
                ON rating_norm(instrument_key);

            CREATE TABLE IF NOT EXISTS financial_norm (
                doc_id                  TEXT NOT NULL,
                row_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_key              TEXT,
                raw_label               TEXT,
                normalized_label        TEXT,
                classification_status   TEXT,
                period                  TEXT,
                period_year             INTEGER,
                period_month            INTEGER,
                value                   REAL,
                value_raw               TEXT,
                unit                    TEXT,
                value_type              TEXT,
                basis                   TEXT,
                page                    INTEGER,
                row_index               INTEGER,
                col_index               INTEGER,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            );
            CREATE INDEX IF NOT EXISTS idx_financial_norm_doc
                ON financial_norm(doc_id);
            CREATE INDEX IF NOT EXISTS idx_financial_norm_metric
                ON financial_norm(metric_key);
            """
        )
        conn.commit()
    return path


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def upsert_document_result(
    result: dict[str, Any],
    *,
    db_path: Path | None = None,
) -> Path:
    """단일 PDF 결과의 documents / raw / norm 을 upsert."""
    path = init_document_db(db_path)
    file_hash = result.get("file_hash")
    if not file_hash:
        return path

    doc_id = doc_id_from_hash(str(file_hash))
    fin_tables = [
        ExtractedFinTable.from_dict(item)
        for item in (result.get("financial_tables") or [])
    ]
    all_grids = list(result.get("tables") or [])
    facts_payload = result.get("financial_facts") or []
    products = list(result.get("products") or [])

    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO documents (
                doc_id, file_hash, file_name, file_path, company_name, agency,
                evaluation_date, status, fail_reason_json, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                file_hash=excluded.file_hash,
                file_name=excluded.file_name,
                file_path=excluded.file_path,
                company_name=excluded.company_name,
                agency=excluded.agency,
                evaluation_date=excluded.evaluation_date,
                status=excluded.status,
                fail_reason_json=excluded.fail_reason_json,
                processed_at=excluded.processed_at
            """,
            (
                doc_id,
                file_hash,
                result.get("file_name"),
                result.get("file_path"),
                result.get("company_name"),
                result.get("agency"),
                result.get("evaluation_date"),
                result.get("status"),
                _json_or_none(result.get("fail_reason")),
                _now_iso(),
            ),
        )

        for table_name in (
            "rating_grids_raw",
            "financial_grids_raw",
            "rating_norm",
            "financial_norm",
        ):
            conn.execute(
                f"DELETE FROM {table_name} WHERE doc_id = ?",
                (doc_id,),
            )

        section_counters: dict[str, int] = {}
        for grid in all_grids:
            section_key = str(grid.get("section_key") or "unknown")
            if section_key not in _RATING_SECTION_KEYS:
                continue
            table_index = section_counters.get(section_key, 0)
            section_counters[section_key] = table_index + 1
            conn.execute(
                """
                INSERT INTO rating_grids_raw (
                    doc_id, section_key, table_index, page, title_raw,
                    region_id, source, headers_json, rows_json, bbox_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    section_key,
                    table_index,
                    grid.get("page"),
                    grid.get("title_raw"),
                    grid.get("region_id"),
                    grid.get("source"),
                    json.dumps(grid.get("headers") or [], ensure_ascii=False),
                    json.dumps(grid.get("rows") or [], ensure_ascii=False),
                    _json_or_none(grid.get("bbox")),
                ),
            )

        # 재무 raw: financial_tables 우선, 없으면 tables 중 financial 섹션
        if fin_tables:
            for index, table in enumerate(fin_tables):
                conn.execute(
                    """
                    INSERT INTO financial_grids_raw (
                        doc_id, table_index, page, title_raw, source, basis,
                        unit_caption, footnotes_json, headers_json, rows_json,
                        bbox_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id,
                        index,
                        table.page,
                        table.title_raw,
                        table.source,
                        table.basis,
                        table.unit_caption,
                        json.dumps(table.footnotes, ensure_ascii=False),
                        json.dumps(table.headers, ensure_ascii=False),
                        json.dumps(table.rows, ensure_ascii=False),
                        _json_or_none(table.bbox),
                    ),
                )
        else:
            fin_index = 0
            for grid in all_grids:
                if str(grid.get("section_key") or "") != SECTION_FINANCIAL:
                    continue
                conn.execute(
                    """
                    INSERT INTO financial_grids_raw (
                        doc_id, table_index, page, title_raw, source, basis,
                        unit_caption, footnotes_json, headers_json, rows_json,
                        bbox_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id,
                        fin_index,
                        grid.get("page"),
                        grid.get("title_raw"),
                        grid.get("source"),
                        grid.get("basis"),
                        grid.get("unit_caption"),
                        json.dumps(
                            grid.get("footnotes") or [], ensure_ascii=False
                        ),
                        json.dumps(
                            grid.get("headers") or [], ensure_ascii=False
                        ),
                        json.dumps(grid.get("rows") or [], ensure_ascii=False),
                        _json_or_none(grid.get("bbox")),
                    ),
                )
                fin_index += 1

        for product in products:
            conn.execute(
                """
                INSERT INTO rating_norm (
                    doc_id, instrument_key, raw_label, normalized_label,
                    rating, outlook, evaluation_type, status,
                    fail_reason_json, page, source, rating_status, section
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    product.get("instrument_key"),
                    product.get("raw_label"),
                    product.get("normalized_label"),
                    product.get("rating"),
                    product.get("outlook"),
                    product.get("evaluation_type"),
                    product.get("status"),
                    _json_or_none(product.get("fail_reason")),
                    product.get("page"),
                    product.get("source"),
                    product.get("rating_status"),
                    product.get("section"),
                ),
            )

        for fact in facts_payload:
            conn.execute(
                """
                INSERT INTO financial_norm (
                    doc_id, metric_key, raw_label, normalized_label,
                    classification_status, period, period_year, period_month,
                    value, value_raw, unit, value_type, basis, page,
                    row_index, col_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    fact.get("metric_key"),
                    fact.get("raw_label"),
                    fact.get("normalized_label"),
                    fact.get("classification_status"),
                    fact.get("period"),
                    fact.get("period_year"),
                    fact.get("period_month"),
                    fact.get("value"),
                    fact.get("value_raw"),
                    fact.get("unit"),
                    fact.get("value_type"),
                    fact.get("basis"),
                    fact.get("page"),
                    fact.get("row_index"),
                    fact.get("col_index"),
                ),
            )
        conn.commit()
    return path


def persist_batch_documents(
    results: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
) -> Path:
    path = init_document_db(db_path)
    for result in results:
        upsert_document_result(result, db_path=path)
    return path


def load_raw_tables(
    doc_key: str,
    *,
    db_path: Path | None = None,
) -> list[ExtractedFinTable]:
    """financial_grids_raw 로드. doc_key는 doc_id 또는 file_hash(앞 16자 사용)."""
    path = init_document_db(db_path)
    doc_id = doc_id_from_hash(doc_key)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM financial_grids_raw
            WHERE doc_id = ?
            ORDER BY table_index
            """,
            (doc_id,),
        ).fetchall()
    tables: list[ExtractedFinTable] = []
    for row in rows:
        bbox = json.loads(row["bbox_json"]) if row["bbox_json"] else None
        tables.append(
            ExtractedFinTable(
                page=int(row["page"] or 0),
                title_raw=row["title_raw"] or "",
                headers=json.loads(row["headers_json"] or "[]"),
                rows=json.loads(row["rows_json"] or "[]"),
                source=row["source"] or "pdf_table",
                basis=row["basis"],
                unit_caption=row["unit_caption"],
                footnotes=json.loads(row["footnotes_json"] or "[]"),
                bbox=tuple(bbox) if bbox else None,
            )
        )
    return tables


def replace_financial_norm(
    doc_key: str,
    facts: list[FinancialFact],
    *,
    db_path: Path | None = None,
) -> None:
    """financial_norm 행을 교체. doc_key는 doc_id 또는 file_hash."""
    path = init_document_db(db_path)
    doc_id = doc_id_from_hash(doc_key)
    with _connect(path) as conn:
        conn.execute(
            "DELETE FROM financial_norm WHERE doc_id = ?",
            (doc_id,),
        )
        for fact in facts:
            payload = fact.to_dict()
            conn.execute(
                """
                INSERT INTO financial_norm (
                    doc_id, metric_key, raw_label, normalized_label,
                    classification_status, period, period_year, period_month,
                    value, value_raw, unit, value_type, basis, page,
                    row_index, col_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    payload.get("metric_key"),
                    payload.get("raw_label"),
                    payload.get("normalized_label"),
                    payload.get("classification_status"),
                    payload.get("period"),
                    payload.get("period_year"),
                    payload.get("period_month"),
                    payload.get("value"),
                    payload.get("value_raw"),
                    payload.get("unit"),
                    payload.get("value_type"),
                    payload.get("basis"),
                    payload.get("page"),
                    payload.get("row_index"),
                    payload.get("col_index"),
                ),
            )
        conn.commit()


# 하위 호환 alias
replace_financial_facts = replace_financial_norm


def list_document_ids(*, db_path: Path | None = None) -> list[str]:
    path = init_document_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT doc_id FROM documents ORDER BY processed_at DESC"
        ).fetchall()
    return [str(row["doc_id"]) for row in rows]


def list_document_hashes(*, db_path: Path | None = None) -> list[str]:
    """하위 호환: file_hash 목록 (renormalize용)."""
    path = init_document_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT file_hash FROM documents ORDER BY processed_at DESC"
        ).fetchall()
    return [str(row["file_hash"]) for row in rows]


def renormalize_all(
    *,
    db_path: Path | None = None,
    classifier: MetricClassifier | None = None,
) -> dict[str, int]:
    """DB financial_grids_raw만으로 financial_norm 재생성."""
    from common.settings import clear_config_caches

    clear_config_caches()
    active = classifier or MetricClassifier.from_yaml()
    path = init_document_db(db_path)
    doc_ids = list_document_ids(db_path=path)
    fact_count = 0
    for doc_id in doc_ids:
        tables = load_raw_tables(doc_id, db_path=path)
        facts, _undefined = facts_from_fin_tables(tables, active)
        replace_financial_norm(doc_id, facts, db_path=path)
        fact_count += len(facts)
    return {"documents": len(doc_ids), "facts": fact_count}
