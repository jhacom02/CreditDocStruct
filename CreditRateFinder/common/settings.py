"""`.env` 로드 및 `config/instruments.yaml` 로드·기동 시 검증.

경로·상수는 이 모듈을 통해서만 읽는다(코드에 하드코딩하지 않음).
매칭 정책(정규화·추천·검증)은 `common.matching_policy`가 단일 원천이다.
`instruments.yaml`은 상품·라벨 딕셔너리만 보관한다.

`target_instrument`/`DEFAULT_TARGET_INSTRUMENT` 개념은 없다: 사용자는
대상 상품을 지정하지 않고, PDF에서 실제 검출된 라벨을 자동 탐색해
YAML로 분류한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from common.matching_policy import MatchingPolicyError, build_normalized_lookup

APP_ROOT = Path(__file__).resolve().parent.parent

# 결과 파일명 접두어 → {접두어}_YYYYMMDD.json / .xlsx (코드 고정)
RESULT_FILENAME_PREFIX = "result"


@dataclass(frozen=True)
class Settings:
    """`.env`에서 로드한 애플리케이션 설정."""

    # PDF 입력 폴더. 코드 기본값 없음 — .env INPUT_DIR에만 지정.
    input_dir: str | None
    # 폴더/파일을 하나의 경로 변수로 지정 (예: config/instruments.yaml)
    instruments_yaml: str = "config/instruments.yaml"
    result_dir: str = "result"
    admin_db_path: str = "admin/data/admin.db"
    admin_backup_dir: str = "admin/backup"
    max_pdf_pages: int = 1
    min_extracted_text_chars: int = 50

    @staticmethod
    def _resolve_path(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else APP_ROOT / path

    @property
    def input_dir_path(self) -> Path:
        if not self.input_dir:
            raise ValueError(
                ".env에 INPUT_DIR을 지정하세요. "
                "PDF가 모여 있는 폴더 경로입니다(코드 기본값 없음)."
            )
        return self._resolve_path(self.input_dir)

    @property
    def instruments_yaml_path(self) -> Path:
        return self._resolve_path(self.instruments_yaml)

    @property
    def result_dir_path(self) -> Path:
        return self._resolve_path(self.result_dir)

    @property
    def admin_db_path_resolved(self) -> Path:
        return self._resolve_path(self.admin_db_path)

    @property
    def admin_backup_dir_path(self) -> Path:
        return self._resolve_path(self.admin_backup_dir)


def _load_dotenv_once() -> None:
    load_dotenv(APP_ROOT / ".env")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv_once()
    input_dir = (os.environ.get("INPUT_DIR") or "").strip() or None
    return Settings(
        input_dir=input_dir,
        instruments_yaml=os.environ.get(
            "INSTRUMENTS_YAML_PATH", "config/instruments.yaml"
        ),
        result_dir=os.environ.get("RESULT_DIR", "result"),
        admin_db_path=os.environ.get(
            "ADMIN_DB_PATH", "admin/data/admin.db"
        ),
        admin_backup_dir=os.environ.get(
            "ADMIN_BACKUP_DIR", "admin/backup"
        ),
        max_pdf_pages=int(os.environ.get("MAX_PDF_PAGES", "1")),
        min_extracted_text_chars=int(
            os.environ.get("MIN_EXTRACTED_TEXT_CHARS", "50")
        ),
    )


@dataclass(frozen=True)
class InstrumentDefinition:
    key: str
    display_name: str


@dataclass(frozen=True)
class LabelDictionaryEntry:
    raw_label: str
    instrument_key: str
    active: bool = True
    note: str = ""


@dataclass(frozen=True)
class InstrumentsConfig:
    """`config/instruments.yaml`의 상품·라벨 카탈로그."""

    instruments: dict[str, InstrumentDefinition]
    label_dictionary: tuple[LabelDictionaryEntry, ...]
    normalized_lookup: dict[str, str]


class InstrumentsConfigError(ValueError):
    """`config/instruments.yaml` 기동 시 검증 실패."""


def _build_instruments(
    raw: dict[str, Any],
) -> dict[str, InstrumentDefinition]:
    instruments: dict[str, InstrumentDefinition] = {}
    for key, spec in (raw or {}).items():
        spec = spec or {}
        instruments[key] = InstrumentDefinition(
            key=key,
            display_name=spec.get("display_name", key),
        )
    return instruments


def _build_label_dictionary(
    raw: dict[str, Any],
) -> list[LabelDictionaryEntry]:
    entries: list[LabelDictionaryEntry] = []
    for raw_label, spec in (raw or {}).items():
        spec = spec or {}
        instrument_key = spec.get("instrument_key")
        if not instrument_key:
            continue
        entries.append(
            LabelDictionaryEntry(
                raw_label=raw_label,
                instrument_key=instrument_key,
                active=bool(spec.get("active", True)),
                note=spec.get("note", "") or "",
            )
        )
    return entries


def _validate(
    instruments: dict[str, InstrumentDefinition],
    entries: list[LabelDictionaryEntry],
) -> dict[str, str]:
    """알 수 없는 instrument_key 참조 거부, 동일 정규화 라벨의 상충 매핑 거부."""
    try:
        return build_normalized_lookup(instruments, entries)
    except MatchingPolicyError as exc:
        raise InstrumentsConfigError(
            f"config/instruments.yaml 검증 실패: {exc}"
        ) from exc


def load_instruments_config(path: Path | None = None) -> InstrumentsConfig:
    """검증 실패 시 `InstrumentsConfigError`를 던진다(캐시 없이 매번 로드).

    `instruments`·`label_dictionary`만 소비한다. 구 백업에 남아 있는
    normalization/recommendation/validation 등 여분 최상위 키는 무시한다.
    """
    settings = get_settings()
    yaml_path = path or settings.instruments_yaml_path

    with yaml_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise InstrumentsConfigError(
            "config/instruments.yaml 최상위는 객체여야 합니다."
        )

    instruments = _build_instruments(raw.get("instruments") or {})
    entries = _build_label_dictionary(raw.get("label_dictionary") or {})
    normalized_lookup = _validate(instruments, entries)

    return InstrumentsConfig(
        instruments=instruments,
        label_dictionary=tuple(entries),
        normalized_lookup=normalized_lookup,
    )


@lru_cache(maxsize=1)
def get_instruments_config() -> InstrumentsConfig:
    return load_instruments_config()
