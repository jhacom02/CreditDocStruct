"""기존 admin/undefined.json → SQLite 1회 이관."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from common.settings import get_settings, load_instruments_config
from admin.services.candidate_store import init_db, upsert_occurrences


def _map_entry(
    entry: dict[str, Any],
    *,
    normalized_lookup: dict[str, str],
) -> tuple[dict[str, Any], str]:
    normalized = entry.get("normalized_label") or ""
    raw_labels = entry.get("raw_labels") or []
    raw_label = raw_labels[-1] if raw_labels else normalized

    status = entry.get("review_status") or "pending"
    if status not in {"pending", "approved", "ignored"}:
        status = "pending"
    if normalized in normalized_lookup:
        status = "approved"

    occurrence_ids = entry.get("occurrence_ids") or []
    occurrence_id = occurrence_ids[-1] if occurrence_ids else None

    occurrence = {
        "occurrence_id": occurrence_id,
        "normalized_label": normalized,
        "raw_label": raw_label,
        "file_name": (entry.get("sample_files") or [None])[0],
        "agency": (entry.get("sample_agencies") or [None])[0],
        "rating": (entry.get("sample_ratings") or [None])[0],
        "suggestions": entry.get("suggestions") or [],
    }
    return occurrence, status


def migrate(
    source: Path,
    *,
    db_path: Path | None = None,
) -> int:
    if not source.exists():
        raise FileNotFoundError(f"소스 파일이 없습니다: {source}")

    with source.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    entries = data.get("entries") or []
    config = load_instruments_config()
    path = init_db(db_path)

    migrated = 0
    for entry in entries:
        normalized = entry.get("normalized_label") or ""
        if not normalized:
            continue
        occurrence, status = _map_entry(
            entry, normalized_lookup=config.normalized_lookup
        )
        upsert_occurrences([occurrence], db_path=path)

        if status != "pending":
            with sqlite3.connect(path) as conn:
                conn.execute(
                    """
                    UPDATE candidates
                    SET status = ?, review_note = ?, occurrence_count = ?,
                        first_seen_at = COALESCE(?, first_seen_at),
                        last_seen_at = COALESCE(?, last_seen_at)
                    WHERE normalized_label = ?
                    """,
                    (
                        status,
                        entry.get("note") or "",
                        int(entry.get("occurrence_count") or 1),
                        entry.get("first_seen_at"),
                        entry.get("last_seen_at"),
                        normalized,
                    ),
                )
                conn.commit()
        migrated += 1

    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="admin/undefined.json을 SQLite로 이관합니다.",
    )
    parser.add_argument(
        "--source",
        default="admin/undefined.json",
        help="이관할 undefined.json 경로",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="대상 SQLite 경로 (기본: .env ADMIN_DB_PATH)",
    )
    args = parser.parse_args()

    settings = get_settings()
    db_path = Path(args.db) if args.db else settings.admin_db_path_resolved
    count = migrate(Path(args.source), db_path=db_path)
    print(f"이관 완료: {count}건 -> {db_path}")


if __name__ == "__main__":
    main()
