"""admin/undefined.json 누적 병합 (occurrence_id 중복 방지).

Plan: creditratefinder_restructure_43c68190 섹션 B / G-1 참고.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_occurrence_id(
    file_hash: str,
    normalized_label: str,
    page: int,
    row_index: int,
) -> str:
    return f"{file_hash}|{normalized_label}|p{page}|r{row_index}"


def _now_iso() -> str:
    return datetime.now(tz=KST).isoformat(timespec="seconds")


def load_undefined_store(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"schema_version": 1, "updated_at": None, "entries": []}

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        return {"schema_version": 1, "updated_at": None, "entries": []}

    data.setdefault("schema_version", 1)
    data.setdefault("updated_at", None)
    data.setdefault("entries", [])
    return data


def _next_entry_id(entries: list[dict[str, Any]]) -> str:
    max_num = 0
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        if entry_id.startswith("U") and entry_id[1:].isdigit():
            max_num = max(max_num, int(entry_id[1:]))
    return f"U{max_num + 1:06d}"


def merge_undefined_occurrences(
    store: dict[str, Any],
    occurrences: list[dict[str, Any]],
) -> dict[str, Any]:
    """occurrences를 store에 병합한다(동일 occurrence_id는 count 등 갱신 금지).

    occurrence 항목 스키마:
      occurrence_id, normalized_label, raw_label, file_name, agency,
      rating, suggestions
    """
    entries: list[dict[str, Any]] = list(store.get("entries") or [])
    by_label: dict[str, dict[str, Any]] = {
        entry["normalized_label"]: entry
        for entry in entries
        if entry.get("normalized_label")
    }

    now = _now_iso()

    for item in occurrences:
        normalized = item["normalized_label"]
        occurrence_id = item["occurrence_id"]
        entry = by_label.get(normalized)

        if entry is None:
            entry = {
                "id": _next_entry_id(entries),
                "normalized_label": normalized,
                "raw_labels": [],
                "occurrence_ids": [],
                "occurrence_count": 0,
                "first_seen_at": now,
                "last_seen_at": now,
                "sample_files": [],
                "sample_agencies": [],
                "sample_ratings": [],
                "suggestions": item.get("suggestions") or [],
                "review_status": "pending",
                "chosen_instrument_key": None,
                "note": "",
            }
            entries.append(entry)
            by_label[normalized] = entry

        existing_ids = set(entry.get("occurrence_ids") or [])
        if occurrence_id in existing_ids:
            # 중복: count / first_seen / samples 갱신 금지. last_seen만 갱신 가능.
            entry["last_seen_at"] = now
            continue

        entry.setdefault("occurrence_ids", []).append(occurrence_id)
        entry["occurrence_count"] = int(entry.get("occurrence_count") or 0) + 1
        entry["last_seen_at"] = now
        if not entry.get("first_seen_at"):
            entry["first_seen_at"] = now

        raw_label = item.get("raw_label")
        if raw_label and raw_label not in entry.setdefault("raw_labels", []):
            entry["raw_labels"].append(raw_label)

        file_name = item.get("file_name")
        if file_name and file_name not in entry.setdefault("sample_files", []):
            if len(entry["sample_files"]) < 10:
                entry["sample_files"].append(file_name)

        agency = item.get("agency")
        if agency and agency not in entry.setdefault("sample_agencies", []):
            if len(entry["sample_agencies"]) < 10:
                entry["sample_agencies"].append(agency)

        rating = item.get("rating")
        if rating and rating not in entry.setdefault("sample_ratings", []):
            if len(entry["sample_ratings"]) < 10:
                entry["sample_ratings"].append(rating)

        if item.get("suggestions"):
            entry["suggestions"] = item["suggestions"]

    return {
        "schema_version": store.get("schema_version", 1),
        "updated_at": now,
        "entries": entries,
    }


def write_undefined_store_tmp(
    store: dict[str, Any],
    final_path: str | Path,
) -> Path:
    final_path = Path(final_path)
    tmp_path = final_path.with_name(final_path.name + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=2)

    return tmp_path
