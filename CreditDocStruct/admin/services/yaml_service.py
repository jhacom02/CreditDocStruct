"""instruments.yaml 안전 읽기/쓰기 (ruamel.yaml)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ruamel.yaml import YAML

from common.matching_policy import find_alias_conflict, normalize_label
from common.settings import (
    InstrumentsConfigError,
    get_instruments_config,
    get_settings,
    load_instruments_config,
)

KST = ZoneInfo("Asia/Seoul")


class YamlServiceError(ValueError):
    """YAML 수정·검증 실패."""


@dataclass(frozen=True)
class AliasEntry:
    raw_label: str
    instrument_key: str
    active: bool = True
    note: str = ""


@dataclass(frozen=True)
class InstrumentAliases:
    instrument_key: str
    display_name: str
    aliases: tuple[AliasEntry, ...]


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
    return get_settings().instruments_yaml_path


def _resolve_backup_dir(backup_dir: Path | None) -> Path:
    if backup_dir is not None:
        return backup_dir
    return get_settings().admin_backup_dir_path


def load_yaml_document(yaml_path: Path | None = None) -> dict[str, Any]:
    path = _resolve_yaml_path(yaml_path)
    yaml = _yaml_loader()
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle)
    return data if isinstance(data, dict) else {}


def list_instrument_aliases(
    yaml_path: Path | None = None,
) -> list[InstrumentAliases]:
    data = load_yaml_document(yaml_path)
    instruments_raw = data.get("instruments") or {}
    dictionary = data.get("label_dictionary") or {}

    grouped: dict[str, list[AliasEntry]] = {
        key: [] for key in instruments_raw
    }
    for raw_label, spec in dictionary.items():
        spec = spec or {}
        key = spec.get("instrument_key")
        if not key:
            continue
        grouped.setdefault(key, []).append(
            AliasEntry(
                raw_label=str(raw_label),
                instrument_key=key,
                active=bool(spec.get("active", True)),
                note=str(spec.get("note") or ""),
            )
        )

    result: list[InstrumentAliases] = []
    for key, spec in instruments_raw.items():
        spec = spec or {}
        result.append(
            InstrumentAliases(
                instrument_key=key,
                display_name=spec.get("display_name", key),
                aliases=tuple(
                    sorted(grouped.get(key, []), key=lambda e: e.raw_label)
                ),
            )
        )
    return sorted(result, key=lambda item: item.instrument_key)


def load_active_alias_lookup(
    yaml_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """현재 YAML의 active alias를 정규화 키로 조회한다.

    캐시된 설정 대신 파일을 매번 다시 읽어 서버 시작 동기화가 개발자의
    직접 YAML 변경까지 반영하도록 한다.
    """
    config = load_instruments_config(_resolve_yaml_path(yaml_path))
    lookup: dict[str, dict[str, str]] = {}
    for entry in config.label_dictionary:
        if not entry.active:
            continue
        normalized = normalize_label(entry.raw_label)
        if not normalized:
            continue
        lookup[normalized] = {
            "alias": entry.raw_label,
            "instrument_key": entry.instrument_key,
        }
    return lookup


def _backup_yaml(
    yaml_path: Path,
    backup_dir: Path,
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"instruments_{_now_stamp()}.yaml"
    shutil.copy2(yaml_path, backup_path)
    return backup_path


def list_backups(backup_dir: Path | None = None) -> list[dict[str, Any]]:
    directory = _resolve_backup_dir(backup_dir)
    if not directory.exists():
        return []
    files = sorted(
        directory.glob("instruments_*.yaml"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [
        {
            "path": str(path),
            "name": path.name,
            "modified_at": datetime.fromtimestamp(
                path.stat().st_mtime, tz=KST
            ).isoformat(timespec="seconds"),
        }
        for path in files
    ]


def _check_alias_conflicts(
    alias: str,
    instrument_key: str,
    *,
    yaml_path: Path | None = None,
    exclude_raw_label: str | None = None,
) -> None:
    config = load_instruments_config(_resolve_yaml_path(yaml_path))
    message = find_alias_conflict(
        alias,
        instrument_key,
        config.label_dictionary,
        known_instrument_keys=config.instruments.keys(),
        exclude_raw_label=exclude_raw_label,
    )
    if message:
        raise YamlServiceError(message)


def _write_yaml_atomic(
    data: dict[str, Any],
    yaml_path: Path,
    *,
    backup_dir: Path | None = None,
) -> Path:
    backup_path = _backup_yaml(yaml_path, _resolve_backup_dir(backup_dir))
    tmp_path = yaml_path.with_suffix(yaml_path.suffix + ".tmp")
    yaml = _yaml_loader()

    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            yaml.dump(data, handle)
        load_instruments_config(tmp_path)
    except InstrumentsConfigError as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise YamlServiceError(f"YAML 검증 실패: {exc}") from exc
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    os.replace(tmp_path, yaml_path)
    get_instruments_config.cache_clear()
    return backup_path


def add_alias(
    instrument_key: str,
    alias: str,
    *,
    yaml_path: Path | None = None,
    backup_dir: Path | None = None,
    note: str | None = None,
) -> Path:
    """label_dictionary에 alias를 추가하고 백업 경로를 반환한다."""
    path = _resolve_yaml_path(yaml_path)
    _check_alias_conflicts(alias, instrument_key, yaml_path=path)

    data = load_yaml_document(path)
    dictionary = data.setdefault("label_dictionary", {})
    timestamp = datetime.now(tz=KST).isoformat(timespec="seconds")
    dictionary[alias] = {
        "instrument_key": instrument_key,
        "active": True,
        "note": note or f"admin 승인 {timestamp}",
    }
    return _write_yaml_atomic(data, path, backup_dir=backup_dir)


def remove_alias(
    alias: str,
    *,
    yaml_path: Path | None = None,
    backup_dir: Path | None = None,
) -> Path:
    """label_dictionary에서 alias를 삭제하고 백업 경로를 반환한다."""
    path = _resolve_yaml_path(yaml_path)
    data = load_yaml_document(path)
    dictionary = data.get("label_dictionary") or {}
    if alias not in dictionary:
        raise YamlServiceError(f"alias를 찾을 수 없습니다: {alias!r}")

    del dictionary[alias]
    data["label_dictionary"] = dictionary
    return _write_yaml_atomic(data, path, backup_dir=backup_dir)


def restore_from_backup(
    backup_path: str | Path,
    *,
    yaml_path: Path | None = None,
    backup_dir: Path | None = None,
) -> Path:
    """백업 파일로 instruments.yaml을 복원한다."""
    path = _resolve_yaml_path(yaml_path)
    backup = Path(backup_path)
    if not backup.exists():
        raise YamlServiceError(f"백업 파일이 없습니다: {backup}")

    # 현재 파일 백업 후 복원본 검증
    current_backup = _backup_yaml(path, _resolve_backup_dir(backup_dir))
    tmp_path = path.with_suffix(path.suffix + ".restore_tmp")
    shutil.copy2(backup, tmp_path)
    try:
        load_instruments_config(tmp_path)
    except InstrumentsConfigError as exc:
        tmp_path.unlink(missing_ok=True)
        raise YamlServiceError(f"백업 YAML 검증 실패: {exc}") from exc

    os.replace(tmp_path, path)
    get_instruments_config.cache_clear()
    return current_backup
