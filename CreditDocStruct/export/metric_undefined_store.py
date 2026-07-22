"""undefined 재무지표 라벨 저장 (운영 루프 제거 — no-op)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.settings import get_settings


def persist_undefined_metric_occurrences(
    occurrences: list[dict[str, Any]],
    *,
    db_path: Path | None = None,
) -> Path:
    """지표 검수 운영 중단: 저장하지 않고 경로만 반환."""
    del occurrences
    settings = get_settings()
    path = Path(db_path) if db_path is not None else settings.admin_db_path_resolved
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
