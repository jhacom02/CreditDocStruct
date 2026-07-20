"""`.env` 로드 및 `config/instruments.yaml` 로드·기동 시 검증.

경로·상수는 이 모듈을 통해서만 읽는다(코드에 하드코딩하지 않음).
`target_instrument`/`DEFAULT_TARGET_INSTRUMENT` 개념은 없다: 사용자는
대상 상품을 지정하지 않고, PDF에서 실제 검출된 라벨을 자동 탐색해
YAML로 분류한다.

Plan: creditratefinder_restructure_43c68190 섹션 A/C 참고.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .text_utils import normalize_label

APP_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """`.env`에서 로드한 애플리케이션 설정."""

    # PDF 입력 폴더. 코드 기본값 없음 — .env INPUT_DIR에만 지정.
    input_dir: str | None
    config_dir: str = "config"
    instruments_yaml: str = "instruments.yaml"
    result_dir: str = "result"
    result_filename_prefix: str = "result"
    admin_dir: str = "admin"
    undefined_json: str = "undefined.json"
    max_pdf_pages: int = 3
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
    def config_dir_path(self) -> Path:
        return self._resolve_path(self.config_dir)

    @property
    def instruments_yaml_path(self) -> Path:
        return self.config_dir_path / self.instruments_yaml

    @property
    def result_dir_path(self) -> Path:
        return self._resolve_path(self.result_dir)

    @property
    def admin_dir_path(self) -> Path:
        return self._resolve_path(self.admin_dir)

    @property
    def undefined_json_path(self) -> Path:
        return self.admin_dir_path / self.undefined_json


def _load_dotenv_once() -> None:
    load_dotenv(APP_ROOT / ".env")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv_once()
    input_dir = (os.environ.get("INPUT_DIR") or "").strip() or None
    return Settings(
        input_dir=input_dir,
        config_dir=os.environ.get("CONFIG_DIR", "config"),
        instruments_yaml=os.environ.get(
            "INSTRUMENTS_YAML", "instruments.yaml"
        ),
        result_dir=os.environ.get("RESULT_DIR", "result"),
        result_filename_prefix=os.environ.get(
            "RESULT_FILENAME_PREFIX", "result"
        ),
        admin_dir=os.environ.get("ADMIN_DIR", "admin"),
        undefined_json=os.environ.get("UNDEFINED_JSON", "undefined.json"),
        max_pdf_pages=int(os.environ.get("MAX_PDF_PAGES", "3")),
        min_extracted_text_chars=int(
            os.environ.get("MIN_EXTRACTED_TEXT_CHARS", "50")
        ),
    )


@dataclass(frozen=True)
class InstrumentDefinition:
    key: str
    major_category_name: str
    display_name: str


@dataclass(frozen=True)
class LabelDictionaryEntry:
    raw_label: str
    instrument_key: str
    active: bool = True
    note: str = ""


@dataclass(frozen=True)
class InstrumentsConfig:
    """`config/instruments.yaml`을 로드·검증한 결과."""

    instruments: dict[str, InstrumentDefinition]
    label_dictionary: tuple[LabelDictionaryEntry, ...]
    normalized_lookup: dict[str, str]
    normalization: dict[str, Any]
    recommendation: dict[str, Any]
    validation: dict[str, Any]


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
            major_category_name=spec.get("major_category_name", key),
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
                note=spec.get("note", ""),
            )
        )
    return entries


def _validate(
    instruments: dict[str, InstrumentDefinition],
    entries: list[LabelDictionaryEntry],
) -> dict[str, str]:
    """알 수 없는 instrument_key 참조 거부, 동일 정규화 라벨의 상충 매핑 거부."""

    normalized_lookup: dict[str, str] = {}
    conflicts: list[str] = []
    unknown_keys: list[str] = []

    for entry in entries:
        if entry.instrument_key not in instruments:
            unknown_keys.append(
                f"{entry.raw_label!r} -> {entry.instrument_key!r}"
            )
            continue

        if not entry.active:
            continue

        normalized = normalize_label(entry.raw_label)
        existing = normalized_lookup.get(normalized)

        if existing is not None and existing != entry.instrument_key:
            conflicts.append(
                f"{normalized!r}: {existing!r} vs {entry.instrument_key!r}"
            )
            continue

        normalized_lookup[normalized] = entry.instrument_key

    if unknown_keys:
        raise InstrumentsConfigError(
            "config/instruments.yaml에 등록되지 않은 instrument_key 참조: "
            + "; ".join(unknown_keys)
        )

    if conflicts:
        raise InstrumentsConfigError(
            "config/instruments.yaml에서 동일 정규화 라벨이 서로 다른 "
            "instrument_key에 매핑됨: " + "; ".join(conflicts)
        )

    return normalized_lookup


def load_instruments_config(path: Path | None = None) -> InstrumentsConfig:
    """검증 실패 시 `InstrumentsConfigError`를 던진다(캐시 없이 매번 로드)."""

    settings = get_settings()
    yaml_path = path or settings.instruments_yaml_path

    with yaml_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    instruments = _build_instruments(raw.get("instruments") or {})
    entries = _build_label_dictionary(raw.get("label_dictionary") or {})
    normalized_lookup = _validate(instruments, entries)

    return InstrumentsConfig(
        instruments=instruments,
        label_dictionary=tuple(entries),
        normalized_lookup=normalized_lookup,
        normalization=raw.get("normalization") or {},
        recommendation=raw.get("recommendation") or {},
        validation=raw.get("validation") or {},
    )


@lru_cache(maxsize=1)
def get_instruments_config() -> InstrumentsConfig:
    return load_instruments_config()
