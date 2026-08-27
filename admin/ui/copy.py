"""관리자 UI용 사용자 친화 문구·변환 헬퍼."""

from __future__ import annotations

from typing import Any

from common.settings import get_instruments_config


def display_name_for(key: str | None) -> str:
    if not key:
        return "-"
    config = get_instruments_config()
    spec = config.instruments.get(key)
    return spec.display_name if spec else key


def instrument_options() -> list[tuple[str, str]]:
    config = get_instruments_config()
    return [
        (key, spec.display_name)
        for key, spec in sorted(
            config.instruments.items(),
            key=lambda item: item[1].display_name,
        )
    ]


def sort_suggestions(suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        suggestions,
        key=lambda item: float(item.get("score") or 0),
        reverse=True,
    )


def top_suggestions(
    suggestions: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    return sort_suggestions(suggestions)[:limit]


def default_instrument_key(suggestions: list[dict[str, Any]]) -> str | None:
    top = top_suggestions(suggestions, limit=1)
    if not top:
        return None
    return top[0].get("instrument_key")


def friendly_yaml_error(exc: Exception) -> tuple[str, str]:
    detail = str(exc).strip() or "알 수 없는 오류"
    return (
        "라벨을 저장하지 못했습니다.",
        "기존 등록 라벨과 중복되었거나 YAML 파일을 사용할 수 없습니다. "
        f"상세: {detail}",
    )
