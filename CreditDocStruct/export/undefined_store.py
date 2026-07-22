"""undefined 후보를 SQLite에 저장하는 어댑터.

`make_occurrence_id`, `file_sha256`은 추출 파이프라인에서 계속 사용한다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


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


def persist_undefined_occurrences(
    occurrences: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
) -> Path:
    """occurrences를 SQLite에 upsert하고 DB 경로를 반환한다."""
    from admin.services.candidate_store import upsert_occurrences

    return upsert_occurrences(occurrences, db_path=db_path)
