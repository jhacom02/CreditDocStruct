"""metrics.yaml 안전 읽기/쓰기."""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ruamel.yaml import YAML

from common.matching_policy import normalize_metric_label
from common.settings import (
    MetricsConfigError,
    clear_config_caches,
    get_metrics_config,
    get_settings,
    load_metrics_config,
)

KST = ZoneInfo("Asia/Seoul")


class MetricsYamlServiceError(ValueError):
    pass


def _yaml_loader() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def _now_stamp() -> str:
    return datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S_%f")


def _resolve_yaml_path(yaml_path: Path | None) -> Path:
    if yaml_path is not None:
        return yaml_path
    return get_settings().metrics_yaml_path


def _resolve_backup_dir(backup_dir: Path | None) -> Path:
    if backup_dir is not None:
        return backup_dir
    return get_settings().admin_backup_dir_path


def load_metrics_yaml_document(
    yaml_path: Path | None = None,
) -> dict[str, Any]:
    path = _resolve_yaml_path(yaml_path)
    yaml = _yaml_loader()
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle)
    return data if isinstance(data, dict) else {}


def list_metric_options(
    yaml_path: Path | None = None,
) -> list[tuple[str, str]]:
    config = load_metrics_config(_resolve_yaml_path(yaml_path))
    return [
        (key, definition.display_name)
        for key, definition in sorted(
            config.metrics.items(), key=lambda item: item[0]
        )
    ]


def _backup_yaml(yaml_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"metrics_{_now_stamp()}.yaml"
    shutil.copy2(yaml_path, backup_path)
    return backup_path


def add_metric_alias(
    metric_key: str,
    alias: str,
    *,
    yaml_path: Path | None = None,
    backup_dir: Path | None = None,
    note: str | None = None,
) -> Path:
    path = _resolve_yaml_path(yaml_path)
    alias = (alias or "").strip()
    if not alias:
        raise MetricsYamlServiceError("alias가 비어 있습니다.")

    config = load_metrics_config(path)
    if metric_key not in config.metrics:
        raise MetricsYamlServiceError(f"알 수 없는 metric_key: {metric_key!r}")

    normalized = normalize_metric_label(alias)
    existing = config.normalized_lookup.get(normalized)
    if existing is not None and existing != metric_key:
        raise MetricsYamlServiceError(
            f"정규화 충돌: {alias!r} -> {existing!r}"
        )
    if existing == metric_key:
        raise MetricsYamlServiceError(
            f"이미 등록된 alias입니다: {alias!r}"
        )

    data = load_metrics_yaml_document(path)
    dictionary = data.setdefault("metric_label_dictionary", {})
    timestamp = datetime.now(tz=KST).isoformat(timespec="seconds")
    dictionary[alias] = {
        "metric_key": metric_key,
        "active": True,
        "note": note or f"admin 승인 {timestamp}",
    }

    backup_path = _backup_yaml(path, _resolve_backup_dir(backup_dir))
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    yaml = _yaml_loader()
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            yaml.dump(data, handle)
        load_metrics_config(tmp_path)
    except MetricsConfigError as exc:
        tmp_path.unlink(missing_ok=True)
        raise MetricsYamlServiceError(f"YAML 검증 실패: {exc}") from exc
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    os.replace(tmp_path, path)
    clear_config_caches()
    get_metrics_config.cache_clear()
    return backup_path
