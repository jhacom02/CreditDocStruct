"""라벨 매칭 정책의 단일 원천."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class RecommendationPolicy:
    """undefined 라벨 추천 파라미터."""

    ngram_size: int = 2
    top_k: int = 3
    min_score: float = 15.0


RECOMMENDATION = RecommendationPolicy()

_BRACKET_MAP = {
    "（": "(",
    "）": ")",
    "［": "(",
    "］": ")",
    "【": "(",
    "】": ")",
}

_DASH_MAP = {
    "－": "-",
    "−": "-",
    "–": "-",
    "—": "-",
}


class MatchingPolicyError(ValueError):
    """매칭 정책 검증 실패."""


def normalize_text(value: str | None) -> str:
    """사람이 읽을 수 있는 정규화 형태(공백은 단일 스페이스로 유지)."""
    if not value:
        return ""

    text = unicodedata.normalize("NFKC", str(value))

    for source, target in _BRACKET_MAP.items():
        text = text.replace(source, target)
    for source, target in _DASH_MAP.items():
        text = text.replace(source, target)

    text = text.replace("／", "/").replace("：", ":")

    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    text = "".join(
        char.upper() if char.isascii() and char.isalpha() else char
        for char in text
    )

    return text


def normalize_label(value: str | None) -> str:
    """label_dictionary exact match용 lookup 키(공백 완전 제거)."""
    return re.sub(r"\s+", "", normalize_text(value))


_METRIC_UNIT_PAREN_RE = re.compile(
    r"\((?:십억원|억원|백만원|%|％|배|원)\)",
    re.IGNORECASE,
)
_METRIC_FOOTNOTE_RE = re.compile(r"(?:주\s*\d+\s*\)|\(\s*\d+\s*\)|\*+\d*)$")


def normalize_metric_label(value: str | None) -> str:
    """재무지표 라벨 매칭용: 단위 괄호·각주 마커·공백 제거."""
    text = normalize_text(value)
    if not text:
        return ""
    text = _METRIC_UNIT_PAREN_RE.sub("", text)
    text = _METRIC_FOOTNOTE_RE.sub("", text)
    text = text.strip()
    return re.sub(r"\s+", "", text)


def build_normalized_lookup(
    instrument_keys: Mapping[str, Any] | Iterable[str],
    entries: Iterable[Any],
) -> dict[str, str]:
    """active 라벨의 정규화 lookup을 만들고 충돌·미등록 키를 거부한다."""
    known_keys = set(
        instrument_keys.keys()
        if isinstance(instrument_keys, Mapping)
        else instrument_keys
    )
    normalized_lookup: dict[str, str] = {}
    conflicts: list[str] = []
    unknown_keys: list[str] = []

    for entry in entries:
        instrument_key = entry.instrument_key
        raw_label = entry.raw_label
        if instrument_key not in known_keys:
            unknown_keys.append(f"{raw_label!r} -> {instrument_key!r}")
            continue

        if not entry.active:
            continue

        normalized = normalize_label(raw_label)
        if not normalized:
            continue
        existing = normalized_lookup.get(normalized)
        if existing is not None and existing != instrument_key:
            conflicts.append(
                f"{normalized!r}: {existing!r} vs {instrument_key!r}"
            )
            continue
        normalized_lookup[normalized] = instrument_key

    if unknown_keys:
        raise MatchingPolicyError(
            "등록되지 않은 instrument_key 참조: " + "; ".join(unknown_keys)
        )
    if conflicts:
        raise MatchingPolicyError(
            "동일 정규화 라벨이 서로 다른 instrument_key에 매핑됨: "
            + "; ".join(conflicts)
        )
    return normalized_lookup


def find_alias_conflict(
    alias: str,
    instrument_key: str,
    entries: Iterable[Any],
    *,
    known_instrument_keys: Iterable[str],
    exclude_raw_label: str | None = None,
) -> str | None:
    """alias 등록 전 충돌 메시지를 반환한다. 문제 없으면 None."""
    alias = (alias or "").strip()
    if not alias:
        return "alias가 비어 있습니다."

    known = set(known_instrument_keys)
    if instrument_key not in known:
        return f"알 수 없는 instrument_key: {instrument_key!r}"

    for entry in entries:
        if exclude_raw_label and entry.raw_label == exclude_raw_label:
            continue
        if entry.raw_label == alias:
            if entry.instrument_key == instrument_key:
                return f"동일 instrument에 이미 등록된 alias입니다: {alias!r}"
            return (
                f"다른 instrument({entry.instrument_key!r})에 "
                f"이미 등록된 alias입니다: {alias!r}"
            )

    normalized = normalize_label(alias)
    for entry in entries:
        if not entry.active:
            continue
        if exclude_raw_label and entry.raw_label == exclude_raw_label:
            continue
        if normalize_label(entry.raw_label) == normalized:
            if entry.instrument_key != instrument_key:
                return (
                    f"정규화 충돌: {alias!r} -> {entry.instrument_key!r} "
                    f"(기존: {entry.raw_label!r})"
                )
            if entry.raw_label != alias:
                return f"정규화 충돌: {alias!r} (기존: {entry.raw_label!r})"
    return None
