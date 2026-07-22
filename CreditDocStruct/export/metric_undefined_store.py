"""undefined 재무지표 라벨을 SQLite에 저장."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def persist_undefined_metric_occurrences(
    occurrences: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
) -> Path:
    from admin.services.metric_candidate_store import upsert_metric_occurrences

    return upsert_metric_occurrences(occurrences, db_path=db_path)
