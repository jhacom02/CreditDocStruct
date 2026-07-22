"""SQLite 기반 미분류 재무지표 라벨 후보 저장소."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from common.matching_policy import normalize_metric_label
from common.settings import get_settings

KST = ZoneInfo("Asia/Seoul")


def _now_iso() -> str:
    return datetime.now(tz=KST).isoformat(timespec="seconds")


def _get_db_path(db_path: Path | None = None) -> Path:
    if db_path is not None:
        return db_path
    return get_settings().admin_db_path_resolved


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = _get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_metric_db(db_path: Path | None = None) -> Path:
    path = _get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metric_candidates (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_label    TEXT NOT NULL UNIQUE,
                raw_label           TEXT NOT NULL,
                agency              TEXT,
                company_name        TEXT,
                file_name           TEXT,
                occurrence_count    INTEGER NOT NULL DEFAULT 1,
                first_seen_at       TEXT NOT NULL,
                last_seen_at        TEXT NOT NULL,
                last_occurrence_id  TEXT,
                status              TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','approved','ignored')),
                reviewed_at         TEXT,
                review_note         TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_metric_candidates_status
                ON metric_candidates(status);
            """
        )
        conn.commit()
    return path


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def upsert_metric_occurrences(
    occurrences: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
) -> Path:
    path = init_metric_db(db_path)
    if not occurrences:
        return path

    now = _now_iso()
    with _connect(path) as conn:
        for item in occurrences:
            raw = str(item.get("raw_label") or "")
            normalized = normalize_metric_label(
                item.get("normalized_label") or raw
            )
            if not normalized:
                continue
            existing = conn.execute(
                "SELECT * FROM metric_candidates WHERE normalized_label = ?",
                (normalized,),
            ).fetchone()
            occurrence_id = item.get("occurrence_id")
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO metric_candidates (
                        normalized_label, raw_label, agency, company_name,
                        file_name, occurrence_count, first_seen_at,
                        last_seen_at, last_occurrence_id, status
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 'pending')
                    """,
                    (
                        normalized,
                        raw or normalized,
                        item.get("agency"),
                        item.get("company_name"),
                        item.get("file_name"),
                        now,
                        now,
                        occurrence_id,
                    ),
                )
                continue

            if (
                existing["last_occurrence_id"]
                and existing["last_occurrence_id"] == occurrence_id
            ):
                continue
            if existing["status"] == "approved":
                conn.execute(
                    """
                    UPDATE metric_candidates
                    SET last_seen_at = ?, last_occurrence_id = ?,
                        occurrence_count = occurrence_count + 1,
                        file_name = COALESCE(?, file_name),
                        company_name = COALESCE(?, company_name),
                        agency = COALESCE(?, agency)
                    WHERE id = ?
                    """,
                    (
                        now,
                        occurrence_id,
                        item.get("file_name"),
                        item.get("company_name"),
                        item.get("agency"),
                        existing["id"],
                    ),
                )
                continue
            conn.execute(
                """
                UPDATE metric_candidates
                SET last_seen_at = ?, last_occurrence_id = ?,
                    occurrence_count = occurrence_count + 1,
                    raw_label = ?,
                    file_name = COALESCE(?, file_name),
                    company_name = COALESCE(?, company_name),
                    agency = COALESCE(?, agency),
                    status = CASE WHEN status = 'ignored' THEN 'ignored'
                                  ELSE 'pending' END
                WHERE id = ?
                """,
                (
                    now,
                    occurrence_id,
                    raw or existing["raw_label"],
                    item.get("file_name"),
                    item.get("company_name"),
                    item.get("agency"),
                    existing["id"],
                ),
            )
        conn.commit()
    return path


def list_metric_candidates(
    *,
    status: str = "pending",
    agency: str | None = None,
    company_query: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    path = init_metric_db(db_path)
    clauses = ["status = ?"]
    params: list[Any] = [status]
    if agency and agency != "전체":
        clauses.append("agency = ?")
        params.append(agency)
    if company_query:
        clauses.append(
            "(company_name LIKE ? OR file_name LIKE ? OR raw_label LIKE ?)"
        )
        like = f"%{company_query}%"
        params.extend([like, like, like])
    sql = (
        "SELECT * FROM metric_candidates WHERE "
        + " AND ".join(clauses)
        + " ORDER BY last_seen_at DESC"
    )
    with _connect(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def count_metric_by_status(
    *,
    db_path: Path | None = None,
) -> dict[str, int]:
    path = init_metric_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM metric_candidates
            GROUP BY status
            """
        ).fetchall()
    return {str(row["status"]): int(row["cnt"]) for row in rows}


def set_metric_candidate_status(
    candidate_id: int,
    status: str,
    *,
    note: str | None = None,
    db_path: Path | None = None,
) -> None:
    path = init_metric_db(db_path)
    with _connect(path) as conn:
        conn.execute(
            """
            UPDATE metric_candidates
            SET status = ?, reviewed_at = ?, review_note = ?
            WHERE id = ?
            """,
            (status, _now_iso(), note, candidate_id),
        )
        conn.commit()


def get_metric_candidate(
    candidate_id: int,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    path = init_metric_db(db_path)
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM metric_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None
