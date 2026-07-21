"""SQLite 기반 미분류 라벨 후보 저장소."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from common.settings import get_settings
from common.text_utils import normalize_label

KST = ZoneInfo("Asia/Seoul")

CandidateStatus = str  # pending | approved | ignored


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


def init_db(db_path: Path | None = None) -> Path:
    """스키마를 초기화하고 DB 경로를 반환한다."""
    path = _get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_label    TEXT NOT NULL UNIQUE,
                raw_label           TEXT NOT NULL,
                agency              TEXT,
                company_name        TEXT,
                file_name           TEXT,
                rating              TEXT,
                outlook             TEXT,
                evaluation_type     TEXT,
                label_text          TEXT,
                suggestions_json    TEXT NOT NULL DEFAULT '[]',
                occurrence_count    INTEGER NOT NULL DEFAULT 1,
                first_seen_at       TEXT NOT NULL,
                last_seen_at        TEXT NOT NULL,
                last_occurrence_id  TEXT,
                status              TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','approved','ignored')),
                reviewed_at         TEXT,
                review_note         TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_status
                ON candidates(status);
            CREATE INDEX IF NOT EXISTS idx_candidates_last_seen
                ON candidates(last_seen_at DESC);

            CREATE TABLE IF NOT EXISTS review_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id    INTEGER,
                action          TEXT NOT NULL,
                instrument_key  TEXT,
                alias           TEXT,
                previous_value  TEXT,
                new_value       TEXT,
                reviewer        TEXT,
                created_at      TEXT NOT NULL,
                backup_path     TEXT,
                meta_json       TEXT
            );
            """
        )
        conn.commit()
    return path


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    suggestions = data.get("suggestions_json") or "[]"
    try:
        data["suggestions"] = json.loads(suggestions)
    except json.JSONDecodeError:
        data["suggestions"] = []
    return data


def _fetch_one(
    conn: sqlite3.Connection,
    normalized_label: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM candidates WHERE normalized_label = ?",
        (normalized_label,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def upsert_occurrences(
    occurrences: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
) -> Path:
    """undefined 발생 건을 SQLite에 upsert한다."""
    path = init_db(db_path)
    if not occurrences:
        return path

    now = _now_iso()
    with _connect(path) as conn:
        for item in occurrences:
            normalized = item.get("normalized_label") or ""
            if not normalized:
                continue

            occurrence_id = item.get("occurrence_id")
            existing = _fetch_one(conn, normalized)

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO candidates (
                        normalized_label, raw_label, agency, company_name,
                        file_name, rating, outlook, evaluation_type, label_text,
                        suggestions_json, occurrence_count,
                        first_seen_at, last_seen_at, last_occurrence_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'pending')
                    """,
                    (
                        normalized,
                        item.get("raw_label") or normalized,
                        item.get("agency"),
                        item.get("company_name"),
                        item.get("file_name"),
                        item.get("rating"),
                        item.get("outlook"),
                        item.get("evaluation_type"),
                        item.get("label_text"),
                        json.dumps(
                            item.get("suggestions") or [],
                            ensure_ascii=False,
                        ),
                        now,
                        now,
                        occurrence_id,
                    ),
                )
                continue

            same_occurrence = (
                occurrence_id
                and occurrence_id == existing.get("last_occurrence_id")
            )
            new_count = existing["occurrence_count"]
            if not same_occurrence:
                new_count += 1

            conn.execute(
                """
                UPDATE candidates SET
                    raw_label = ?,
                    agency = ?,
                    company_name = ?,
                    file_name = ?,
                    rating = ?,
                    outlook = ?,
                    evaluation_type = ?,
                    label_text = ?,
                    suggestions_json = ?,
                    occurrence_count = ?,
                    last_seen_at = ?,
                    last_occurrence_id = ?
                WHERE normalized_label = ?
                """,
                (
                    item.get("raw_label") or existing["raw_label"],
                    item.get("agency") or existing.get("agency"),
                    item.get("company_name") or existing.get("company_name"),
                    item.get("file_name") or existing.get("file_name"),
                    item.get("rating") or existing.get("rating"),
                    item.get("outlook") or existing.get("outlook"),
                    item.get("evaluation_type")
                    or existing.get("evaluation_type"),
                    item.get("label_text") or existing.get("label_text"),
                    json.dumps(
                        item.get("suggestions")
                        or existing.get("suggestions")
                        or [],
                        ensure_ascii=False,
                    ),
                    new_count,
                    now,
                    occurrence_id or existing.get("last_occurrence_id"),
                    normalized,
                ),
            )
        conn.commit()
    return path


def list_candidates_by_status(
    status: CandidateStatus,
    *,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    path = init_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM candidates
            WHERE status = ?
            ORDER BY last_seen_at DESC
            """,
            (status,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_pending(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    return list_candidates_by_status("pending", db_path=db_path)


def list_ignored(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    return list_candidates_by_status("ignored", db_path=db_path)


def get_candidate_by_id(
    candidate_id: int,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    path = init_db(db_path)
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def count_by_status(*, db_path: Path | None = None) -> dict[str, int]:
    path = init_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM candidates GROUP BY status"
        ).fetchall()
    counts = {"pending": 0, "approved": 0, "ignored": 0}
    for row in rows:
        counts[row["status"]] = row["cnt"]
    return counts


def _insert_sync_history(
    conn: sqlite3.Connection,
    *,
    candidate_id: int,
    action: str,
    instrument_key: str | None,
    alias: str | None,
    previous_value: str,
    new_value: str,
    created_at: str,
    meta: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO review_history (
            candidate_id, action, instrument_key, alias,
            previous_value, new_value, reviewer, created_at,
            backup_path, meta_json
        ) VALUES (?, ?, ?, ?, ?, ?, 'system', ?, NULL, ?)
        """,
        (
            candidate_id,
            action,
            instrument_key,
            alias,
            previous_value,
            new_value,
            created_at,
            json.dumps(meta, ensure_ascii=False) if meta else None,
        ),
    )


def reconcile_candidate_statuses(
    alias_lookup: dict[str, dict[str, str]],
    *,
    db_path: Path | None = None,
) -> dict[str, int]:
    """YAML alias와 후보 상태를 양방향으로 멱등 동기화한다.

    - pending 후보의 normalized_label이 YAML에 있으면 approved
    - approved 후보의 승인 alias가 YAML에서 사라지면 pending
    - 승인 alias의 instrument가 바뀌면 승인 연결 이력만 새 값으로 갱신
    - ignored 후보는 변경하지 않음

    상태나 승인 연결이 실제로 달라질 때만 이력을 추가하므로 반복 실행해도
    추가 변경이 발생하지 않는다.
    """
    path = init_db(db_path)
    now = _now_iso()
    stats = {
        "approved": 0,
        "reopened": 0,
        "reassigned": 0,
        "history_backfilled": 0,
        "skipped_no_history": 0,
    }

    with _connect(path) as conn:
        approved_rows = conn.execute(
            """
            SELECT
                c.id,
                c.normalized_label,
                c.raw_label,
                h.alias AS approved_alias,
                h.instrument_key AS approved_instrument_key
            FROM candidates AS c
            LEFT JOIN review_history AS h
              ON h.id = (
                  SELECT rh.id
                  FROM review_history AS rh
                  WHERE rh.candidate_id = c.id
                    AND rh.action IN (
                        'approve', 'sync_approve', 'sync_reassign'
                    )
                  ORDER BY rh.id DESC
                  LIMIT 1
              )
            WHERE c.status = 'approved'
            """
        ).fetchall()

        for row in approved_rows:
            approved_alias = row["approved_alias"]
            approved_key = row["approved_instrument_key"]
            target: dict[str, str] | None = None

            if approved_alias and approved_key:
                target = alias_lookup.get(normalize_label(approved_alias))
                if target is None:
                    # 승인 때 편집한 alias가 없어도 원 추출 라벨이 현재 YAML에
                    # 등록되어 있으면 새 YAML 연결로 승인 상태를 유지한다.
                    target = alias_lookup.get(row["normalized_label"])

                if target is None:
                    conn.execute(
                        """
                        UPDATE candidates
                        SET status = 'pending', reviewed_at = ?,
                            review_note = ?
                        WHERE id = ?
                        """,
                        (
                            now,
                            "승인 alias가 현재 YAML에서 제거되어 자동 재검수",
                            row["id"],
                        ),
                    )
                    _insert_sync_history(
                        conn,
                        candidate_id=row["id"],
                        action="sync_reopen",
                        instrument_key=approved_key,
                        alias=approved_alias,
                        previous_value="approved",
                        new_value="pending",
                        created_at=now,
                    )
                    stats["reopened"] += 1
                    continue

                if (
                    target["instrument_key"] != approved_key
                    or target["alias"] != approved_alias
                ):
                    conn.execute(
                        """
                        UPDATE candidates
                        SET reviewed_at = ?, review_note = ?
                        WHERE id = ?
                        """,
                        (
                            now,
                            "현재 YAML alias 매핑으로 승인 연결 자동 갱신",
                            row["id"],
                        ),
                    )
                    _insert_sync_history(
                        conn,
                        candidate_id=row["id"],
                        action="sync_reassign",
                        instrument_key=target["instrument_key"],
                        alias=target["alias"],
                        previous_value=approved_key,
                        new_value=target["instrument_key"],
                        created_at=now,
                        meta={
                            "previous_alias": approved_alias,
                            "new_alias": target["alias"],
                        },
                    )
                    stats["reassigned"] += 1
                continue

            # 마이그레이션 등으로 승인 이력이 없는 기존 행은 YAML에서 원
            # 라벨을 확인할 수 있을 때만 이력을 보완하고, 없으면 안전하게 유지.
            target = alias_lookup.get(row["normalized_label"])
            if target is None:
                stats["skipped_no_history"] += 1
                continue
            _insert_sync_history(
                conn,
                candidate_id=row["id"],
                action="sync_approve",
                instrument_key=target["instrument_key"],
                alias=target["alias"],
                previous_value="approved",
                new_value="approved",
                created_at=now,
                meta={"reason": "approval_history_backfill"},
            )
            stats["history_backfilled"] += 1

        pending_rows = conn.execute(
            """
            SELECT id, normalized_label, raw_label
            FROM candidates
            WHERE status = 'pending'
            """
        ).fetchall()
        for row in pending_rows:
            target = alias_lookup.get(row["normalized_label"])
            if target is None:
                continue
            conn.execute(
                """
                UPDATE candidates
                SET status = 'approved', reviewed_at = ?, review_note = ?
                WHERE id = ?
                """,
                (
                    now,
                    "현재 YAML에 등록된 alias를 확인하여 자동 승인",
                    row["id"],
                ),
            )
            _insert_sync_history(
                conn,
                candidate_id=row["id"],
                action="sync_approve",
                instrument_key=target["instrument_key"],
                alias=target["alias"],
                previous_value="pending",
                new_value="approved",
                created_at=now,
            )
            stats["approved"] += 1

        conn.commit()

    return stats


def set_candidate_status(
    candidate_id: int,
    status: CandidateStatus,
    *,
    review_note: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    path = init_db(db_path)
    now = _now_iso()
    with _connect(path) as conn:
        conn.execute(
            """
            UPDATE candidates
            SET status = ?, reviewed_at = ?, review_note = COALESCE(?, review_note)
            WHERE id = ?
            """,
            (status, now, review_note, candidate_id),
        )
        conn.commit()
    return get_candidate_by_id(candidate_id, db_path=path)


def add_review_history(
    *,
    candidate_id: int | None,
    action: str,
    instrument_key: str | None = None,
    alias: str | None = None,
    previous_value: str | None = None,
    new_value: str | None = None,
    reviewer: str | None = None,
    backup_path: str | None = None,
    meta_json: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> int:
    path = init_db(db_path)
    now = _now_iso()
    with _connect(path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO review_history (
                candidate_id, action, instrument_key, alias,
                previous_value, new_value, reviewer, created_at,
                backup_path, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                action,
                instrument_key,
                alias,
                previous_value,
                new_value,
                reviewer,
                now,
                backup_path,
                json.dumps(meta_json, ensure_ascii=False)
                if meta_json is not None
                else None,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_review_history(
    *,
    limit: int = 200,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    path = init_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM review_history
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("meta_json"):
            try:
                item["meta"] = json.loads(item["meta_json"])
            except json.JSONDecodeError:
                item["meta"] = {}
        result.append(item)
    return result


def get_occurrence_count_by_normalized(
    normalized_label: str,
    *,
    db_path: Path | None = None,
) -> int | None:
    """정규화 라벨의 발견 횟수를 반환한다. 없으면 None."""
    path = init_db(db_path)
    with _connect(path) as conn:
        row = conn.execute(
            """
            SELECT occurrence_count
            FROM candidates
            WHERE normalized_label = ?
            """,
            (normalized_label,),
        ).fetchone()
    if row is None:
        return None
    return int(row["occurrence_count"])


def latest_history_by_instrument(
    *,
    db_path: Path | None = None,
) -> dict[str, str]:
    """상품 키별 최신 변경 시각(ISO) 맵을 반환한다."""
    path = init_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT instrument_key, MAX(created_at) AS latest_at
            FROM review_history
            WHERE instrument_key IS NOT NULL
              AND instrument_key <> ''
            GROUP BY instrument_key
            """
        ).fetchall()
    return {
        str(row["instrument_key"]): str(row["latest_at"])
        for row in rows
        if row["instrument_key"] and row["latest_at"]
    }


def list_distinct_agencies(*, db_path: Path | None = None) -> list[str]:
    path = init_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT agency
            FROM candidates
            WHERE agency IS NOT NULL AND TRIM(agency) <> ''
            ORDER BY agency
            """
        ).fetchall()
    return [str(row["agency"]) for row in rows]
