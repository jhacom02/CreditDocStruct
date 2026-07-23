"""파일 해시·occurrence id 헬퍼.

미분류 라벨 SQLite(admin.db) 저장은 제거됨. JSON `undefined_records`만 유지.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


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
