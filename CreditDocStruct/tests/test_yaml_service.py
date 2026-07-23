"""yaml_service 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from admin.services.yaml_service import (
    MANAGED_BY_ADMIN,
    YamlServiceError,
    add_alias,
    delete_aliases,
    list_backups,
    list_instrument_aliases,
    load_active_alias_lookup,
    load_yaml_document,
    remove_alias,
    restore_from_backup,
)
from common.matching_policy import normalize_label
from common.settings import load_instruments_config


MINIMAL_YAML = """\
# 테스트용 instruments.yaml
instruments:
  issuer:
    display_name: "발행자신용등급"
  senior_unsecured:
    display_name: "무보증사채"

label_dictionary:
  "발행자":
    instrument_key: issuer
    active: true
    note: "기존"
  "선순위무보증사채":
    instrument_key: senior_unsecured
    active: true
    note: "기존"
"""

LEGACY_POLICY_YAML = """\
instruments:
  issuer:
    display_name: "발행자신용등급"

label_dictionary:
  "발행자":
    instrument_key: issuer
    active: true
    note: ""

normalization:
  unicode_form: NFKC

recommendation:
  min_score: 15

validation:
  exact_match_only: true
"""


@pytest.fixture
def yaml_env(tmp_path: Path) -> tuple[Path, Path]:
    yaml_path = tmp_path / "instruments.yaml"
    backup_dir = tmp_path / "backups"
    yaml_path.write_text(MINIMAL_YAML, encoding="utf-8")
    return yaml_path, backup_dir


def test_add_alias_success(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    add_alias(
        "issuer",
        "Issuer Rating",
        yaml_path=yaml_path,
        backup_dir=backup_dir,
        note="관리자 추가",
    )
    data = load_yaml_document(yaml_path)
    entry = data["label_dictionary"]["Issuer Rating"]
    assert entry["instrument_key"] == "issuer"
    assert entry["managed_by"] == MANAGED_BY_ADMIN
    assert entry["note"] == "관리자 추가"
    config = load_instruments_config(yaml_path)
    assert config.normalized_lookup[normalize_label("Issuer Rating")] == "issuer"
    assert "normalization" not in data
    assert "recommendation" not in data
    assert "validation" not in data


def test_load_active_alias_lookup(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, _backup_dir = yaml_env
    lookup = load_active_alias_lookup(yaml_path)
    assert lookup["발행자"] == {
        "alias": "발행자",
        "instrument_key": "issuer",
    }
    assert lookup["선순위무보증사채"]["instrument_key"] == "senior_unsecured"


def test_duplicate_alias_same_instrument(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    with pytest.raises(YamlServiceError, match="이미 등록"):
        add_alias("issuer", "발행자", yaml_path=yaml_path, backup_dir=backup_dir)


def test_conflict_other_instrument(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    with pytest.raises(YamlServiceError, match="다른 instrument"):
        add_alias(
            "issuer",
            "선순위무보증사채",
            yaml_path=yaml_path,
            backup_dir=backup_dir,
        )


def test_empty_alias(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    with pytest.raises(YamlServiceError, match="비어"):
        add_alias("issuer", "  ", yaml_path=yaml_path, backup_dir=backup_dir)


def test_remove_alias(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    remove_alias(
        "발행자",
        yaml_path=yaml_path,
        backup_dir=backup_dir,
        allow_locked=True,
    )
    data = load_yaml_document(yaml_path)
    assert "발행자" not in data["label_dictionary"]


def test_delete_aliases_rejects_locked(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    with pytest.raises(YamlServiceError, match="잠긴 라벨"):
        delete_aliases(
            ["발행자"],
            yaml_path=yaml_path,
            backup_dir=backup_dir,
        )


def test_delete_aliases_admin_only(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    add_alias(
        "issuer",
        "관리자표기",
        yaml_path=yaml_path,
        backup_dir=backup_dir,
        note="메모",
    )
    groups = list_instrument_aliases(yaml_path)
    issuer = next(g for g in groups if g.instrument_key == "issuer")
    admin_entry = next(a for a in issuer.aliases if a.raw_label == "관리자표기")
    assert admin_entry.is_admin_managed
    locked = next(a for a in issuer.aliases if a.raw_label == "발행자")
    assert not locked.is_admin_managed

    delete_aliases(
        ["관리자표기"],
        yaml_path=yaml_path,
        backup_dir=backup_dir,
    )
    data = load_yaml_document(yaml_path)
    assert "관리자표기" not in data["label_dictionary"]
    assert "발행자" in data["label_dictionary"]


def test_backup_created(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    add_alias("issuer", "ICR", yaml_path=yaml_path, backup_dir=backup_dir)
    backups = list_backups(backup_dir)
    assert len(backups) == 1
    assert backups[0]["name"].startswith("instruments_")


def test_invalid_yaml_keeps_original(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    original = yaml_path.read_text(encoding="utf-8")
    with pytest.raises(YamlServiceError):
        add_alias(
            "unknown_key",
            "잘못된라벨",
            yaml_path=yaml_path,
            backup_dir=backup_dir,
        )
    assert yaml_path.read_text(encoding="utf-8") == original


def test_atomic_replace(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    add_alias("issuer", "Corporate", yaml_path=yaml_path, backup_dir=backup_dir)
    assert not yaml_path.with_suffix(yaml_path.suffix + ".tmp").exists()
    config = load_instruments_config(yaml_path)
    assert "Corporate" in {e.raw_label for e in config.label_dictionary}


def test_preserves_comments(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    add_alias("issuer", "New Label", yaml_path=yaml_path, backup_dir=backup_dir)
    content = yaml_path.read_text(encoding="utf-8")
    assert "# 테스트용 instruments.yaml" in content


def test_restore_from_backup(yaml_env: tuple[Path, Path]) -> None:
    yaml_path, backup_dir = yaml_env
    add_alias(
        "issuer", "복원테스트", yaml_path=yaml_path, backup_dir=backup_dir
    )
    backup_path = add_alias(
        "issuer", "추가라벨", yaml_path=yaml_path, backup_dir=backup_dir
    )
    restore_from_backup(
        backup_path, yaml_path=yaml_path, backup_dir=backup_dir
    )
    data = load_yaml_document(yaml_path)
    assert "추가라벨" not in data["label_dictionary"]
    assert "복원테스트" in data["label_dictionary"]


def test_load_ignores_legacy_policy_sections(tmp_path: Path) -> None:
    yaml_path = tmp_path / "legacy.yaml"
    yaml_path.write_text(LEGACY_POLICY_YAML, encoding="utf-8")
    config = load_instruments_config(yaml_path)
    assert "발행자" in {e.raw_label for e in config.label_dictionary}
    assert not hasattr(config, "recommendation")


def test_restore_legacy_policy_backup(tmp_path: Path) -> None:
    yaml_path = tmp_path / "instruments.yaml"
    backup_dir = tmp_path / "backups"
    yaml_path.write_text(MINIMAL_YAML, encoding="utf-8")
    legacy_backup = backup_dir / "instruments_legacy.yaml"
    backup_dir.mkdir(parents=True, exist_ok=True)
    legacy_backup.write_text(LEGACY_POLICY_YAML, encoding="utf-8")

    restore_from_backup(
        legacy_backup,
        yaml_path=yaml_path,
        backup_dir=backup_dir,
    )
    config = load_instruments_config(yaml_path)
    assert config.normalized_lookup[normalize_label("발행자")] == "issuer"
    data = load_yaml_document(yaml_path)
    assert "normalization" in data  # 구 백업 원문 유지, 로더는 무시
