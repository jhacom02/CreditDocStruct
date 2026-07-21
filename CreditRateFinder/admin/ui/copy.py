"""관리자 UI용 사용자 친화 문구·변환 헬퍼."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from common.settings import get_instruments_config


ACTION_LABELS = {
    "approve": "라벨 등록",
    "ignore": "라벨 제외",
    "unignore": "다시 검수",
    "add_alias": "라벨 등록",
    "delete_alias": "라벨 삭제",
    "restore_yaml": "백업 복원",
    "sync_approve": "기존 등록 라벨 동기화",
    "sync_reopen": "승인 라벨 재검수",
    "sync_reassign": "승인 연결 갱신",
}

SYSTEM_ACTIONS = frozenset(
    {"sync_approve", "sync_reopen", "sync_reassign"}
)


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


def recommendation_strength(score: float | int | None) -> str:
    if score is None:
        return "추천 정보 없음"
    value = float(score)
    if value >= 60:
        return "비교적 유사함"
    if value >= 30:
        return "확인 필요"
    return "추천 신뢰 낮음"


def format_datetime(value: str | None) -> str:
    if not value:
        return "-"
    text = str(value).strip()
    try:
        cleaned = text
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        return dt.strftime("%Y.%m.%d %H:%M")
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            cleaned = text
            if fmt.endswith("%z") and text.endswith("Z"):
                cleaned = text[:-1] + "+0000"
            if fmt.endswith("%z") and len(cleaned) >= 3 and cleaned[-3] == ":":
                cleaned = cleaned[:-3] + cleaned[-2:]
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y.%m.%d %H:%M")
        except ValueError:
            continue
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        time_part = time_part.split("+", 1)[0].split("-", 1)[0][:5]
        return f"{date_part.replace('-', '.')} {time_part}"
    return text.replace("-", ".")


def action_label(action: str | None) -> str:
    if not action:
        return "작업"
    return ACTION_LABELS.get(action, action)


def is_system_action(action: str | None) -> bool:
    return (action or "") in SYSTEM_ACTIONS


def history_sentence(item: dict[str, Any]) -> str:
    action = item.get("action") or ""
    alias = item.get("alias") or item.get("new_value") or item.get("previous_value")
    product = display_name_for(item.get("instrument_key"))

    if action in {"approve", "add_alias"}:
        return f"“{alias}”을(를) “{product}”에 등록했습니다."
    if action == "ignore":
        return f"“{alias}”을(를) 제외했습니다."
    if action == "unignore":
        return f"“{alias}”을(를) 다시 검수 대기로 옮겼습니다."
    if action == "delete_alias":
        return f"“{alias}” 등록 라벨을 “{product}”에서 삭제했습니다."
    if action == "restore_yaml":
        backup = item.get("previous_value") or "선택한 백업"
        return f"“{backup}” 백업으로 라벨 사전을 복원했습니다."
    if action == "sync_approve":
        return f"“{alias}”이(가) 이미 등록되어 있어 “{product}”로 동기화했습니다."
    if action == "sync_reopen":
        return f"“{alias}” 등록이 사라져 검수 대기로 되돌렸습니다."
    if action == "sync_reassign":
        return f"“{alias}” 연결을 “{product}”로 갱신했습니다."
    return f"{action_label(action)} 작업을 수행했습니다."


def friendly_yaml_error(exc: Exception) -> tuple[str, str]:
    detail = str(exc).strip() or "알 수 없는 오류"
    return (
        "라벨을 저장하지 못했습니다.",
        "기존 등록 라벨과 중복되었거나 YAML 파일을 사용할 수 없습니다. "
        f"상세: {detail}",
    )


def within_seen_period(last_seen_at: str | None, period: str) -> bool:
    if period == "전체" or not last_seen_at:
        return True
    try:
        text = str(last_seen_at)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except ValueError:
        return True
    now = datetime.now(tz=dt.tzinfo) if dt.tzinfo else datetime.now()
    delta_days = (now - dt).total_seconds() / 86400.0
    if period == "오늘":
        return delta_days < 1
    if period == "최근 7일":
        return delta_days <= 7
    if period == "최근 30일":
        return delta_days <= 30
    return True


def filter_candidates(
    candidates: list[dict[str, Any]],
    *,
    agency: str | None = None,
    company_query: str | None = None,
    period: str = "전체",
) -> list[dict[str, Any]]:
    agency = (agency or "").strip()
    company_query = (company_query or "").strip().lower()
    filtered: list[dict[str, Any]] = []
    for item in candidates:
        if agency and agency != "전체" and (item.get("agency") or "") != agency:
            continue
        company = (item.get("company_name") or "").lower()
        if company_query and company_query not in company:
            continue
        if not within_seen_period(item.get("last_seen_at"), period):
            continue
        filtered.append(item)
    return filtered


def next_index_after_remove(current_index: int, remaining: int) -> int:
    if remaining <= 0:
        return 0
    if current_index >= remaining:
        return remaining - 1
    return current_index


def clamp_index(index: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(index, total - 1))
