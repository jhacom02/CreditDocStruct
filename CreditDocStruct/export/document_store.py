"""PDF 문서·재무지표 raw/facts SQLite 저장소."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from common.models import ExtractedFinTable, FinancialFact
from common.settings import get_settings
from classify.fin_normalize import facts_from_fin_tables
from classify.metric_classifier import MetricClassifier

KST = ZoneInfo("Asia/Seoul")


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
    return conn


def init_document_db(db_path: Path | None = None) -> Path:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                file_hash       TEXT PRIMARY KEY,
                file_name       TEXT,
                file_path       TEXT,
                company_name    TEXT,
                agency          TEXT,
                status          TEXT,
                processed_at    TEXT NOT NULL,
                products_json   TEXT
            );

            CREATE TABLE IF NOT EXISTS fin_tables_raw (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash       TEXT NOT NULL,
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
                UNIQUE(file_hash, table_index),
                FOREIGN KEY(file_hash) REFERENCES documents(file_hash)
            );

            CREATE TABLE IF NOT EXISTS tables_raw (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash       TEXT NOT NULL,
                section_key     TEXT NOT NULL,
                table_index     INTEGER NOT NULL,
                page            INTEGER,
                title_raw       TEXT,
                region_id       TEXT,
                source          TEXT,
                basis           TEXT,
                unit_caption    TEXT,
                footnotes_json  TEXT,
                headers_json    TEXT NOT NULL,
                rows_json       TEXT NOT NULL,
                bbox_json       TEXT,
                grid_json       TEXT NOT NULL,
                UNIQUE(file_hash, section_key, table_index),
                FOREIGN KEY(file_hash) REFERENCES documents(file_hash)
            );

            CREATE TABLE IF NOT EXISTS financial_facts (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash               TEXT NOT NULL,
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
                FOREIGN KEY(file_hash) REFERENCES documents(file_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_fin_facts_hash
                ON financial_facts(file_hash);
            CREATE INDEX IF NOT EXISTS idx_fin_facts_metric
                ON financial_facts(metric_key);
            """
        )
        conn.commit()
    return path


def upsert_document_result(
    result: dict[str, Any],
    *,
    db_path: Path | None = None,
) -> Path:
    """단일 PDF 결과의 documents / raw tables / facts 를 upsert."""
    path = init_document_db(db_path)
    file_hash = result.get("file_hash")
    if not file_hash:
        return path

    tables = [
        ExtractedFinTable.from_dict(item)
        for item in (result.get("financial_tables") or [])
    ]
    all_grids = list(result.get("tables") or [])
    facts_payload = result.get("financial_facts") or []

    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO documents (
                file_hash, file_name, file_path, company_name, agency,
                status, processed_at, products_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_hash) DO UPDATE SET
                file_name=excluded.file_name,
                file_path=excluded.file_path,
                company_name=excluded.company_name,
                agency=excluded.agency,
                status=excluded.status,
                processed_at=excluded.processed_at,
                products_json=excluded.products_json
            """,
            (
                file_hash,
                result.get("file_name"),
                result.get("file_path"),
                result.get("company_name"),
                result.get("agency"),
                result.get("status"),
                _now_iso(),
                json.dumps(result.get("products") or [], ensure_ascii=False),
            ),
        )
        conn.execute(
            "DELETE FROM fin_tables_raw WHERE file_hash = ?",
            (file_hash,),
        )
        conn.execute(
            "DELETE FROM tables_raw WHERE file_hash = ?",
            (file_hash,),
        )
        conn.execute(
            "DELETE FROM financial_facts WHERE file_hash = ?",
            (file_hash,),
        )
        for index, table in enumerate(tables):
            conn.execute(
                """
                INSERT INTO fin_tables_raw (
                    file_hash, table_index, page, title_raw, source, basis,
                    unit_caption, footnotes_json, headers_json, rows_json,
                    bbox_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_hash,
                    index,
                    table.page,
                    table.title_raw,
                    table.source,
                    table.basis,
                    table.unit_caption,
                    json.dumps(table.footnotes, ensure_ascii=False),
                    json.dumps(table.headers, ensure_ascii=False),
                    json.dumps(table.rows, ensure_ascii=False),
                    json.dumps(table.bbox, ensure_ascii=False)
                    if table.bbox
                    else None,
                ),
            )
        section_counters: dict[str, int] = {}
        for grid in all_grids:
            section_key = str(grid.get("section_key") or "unknown")
            table_index = section_counters.get(section_key, 0)
            section_counters[section_key] = table_index + 1
            conn.execute(
                """
                INSERT INTO tables_raw (
                    file_hash, section_key, table_index, page, title_raw,
                    region_id, source, basis, unit_caption, footnotes_json,
                    headers_json, rows_json, bbox_json, grid_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_hash,
                    section_key,
                    table_index,
                    grid.get("page"),
                    grid.get("title_raw"),
                    grid.get("region_id"),
                    grid.get("source"),
                    grid.get("basis"),
                    grid.get("unit_caption"),
                    json.dumps(grid.get("footnotes") or [], ensure_ascii=False),
                    json.dumps(grid.get("headers") or [], ensure_ascii=False),
                    json.dumps(grid.get("rows") or [], ensure_ascii=False),
                    json.dumps(grid.get("bbox"), ensure_ascii=False)
                    if grid.get("bbox")
                    else None,
                    json.dumps(grid, ensure_ascii=False),
                ),
            )
        for fact in facts_payload:
            conn.execute(
                """
                INSERT INTO financial_facts (
                    file_hash, metric_key, raw_label, normalized_label,
                    classification_status, period, period_year, period_month,
                    value, value_raw, unit, value_type, basis, page,
                    row_index, col_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_hash,
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
    file_hash: str,
    *,
    db_path: Path | None = None,
) -> list[ExtractedFinTable]:
    path = init_document_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM fin_tables_raw
            WHERE file_hash = ?
            ORDER BY table_index
            """,
            (file_hash,),
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


def replace_financial_facts(
    file_hash: str,
    facts: list[FinancialFact],
    *,
    db_path: Path | None = None,
) -> None:
    path = init_document_db(db_path)
    with _connect(path) as conn:
        conn.execute(
            "DELETE FROM financial_facts WHERE file_hash = ?",
            (file_hash,),
        )
        for fact in facts:
            payload = fact.to_dict()
            conn.execute(
                """
                INSERT INTO financial_facts (
                    file_hash, metric_key, raw_label, normalized_label,
                    classification_status, period, period_year, period_month,
                    value, value_raw, unit, value_type, basis, page,
                    row_index, col_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_hash,
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


def list_document_hashes(*, db_path: Path | None = None) -> list[str]:
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
    """DB raw 그리드만으로 financial_facts 재생성."""
    from common.settings import clear_config_caches

    clear_config_caches()
    active = classifier or MetricClassifier.from_yaml()
    path = init_document_db(db_path)
    hashes = list_document_hashes(db_path=path)
    fact_count = 0
    for file_hash in hashes:
        tables = load_raw_tables(file_hash, db_path=path)
        facts, _undefined = facts_from_fin_tables(tables, active)
        replace_financial_facts(file_hash, facts, db_path=path)
        fact_count += len(facts)
    return {"documents": len(hashes), "facts": fact_count}
