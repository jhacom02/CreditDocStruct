"""라벨 검수 화면 — 한 건씩 검수 중심."""

from __future__ import annotations

from typing import Any

import streamlit as st

from admin.services.candidate_store import (
    add_review_history,
    list_ignored,
    list_pending,
    set_candidate_status,
)
from admin.ui.copy import (
    clamp_index,
    default_instrument_key,
    display_name_for,
    filter_candidates,
    format_datetime,
    friendly_yaml_error,
    instrument_options,
    next_index_after_remove,
    recommendation_strength,
    top_suggestions,
)
from admin.ui.theme import (
    badge,
    confirm_box,
    label_hero,
    meta_grid,
    progress_bar,
    suggestion_card,
)
from admin.services.yaml_service import YamlServiceError, add_alias


def _init_review_state() -> None:
    defaults = {
        "review_mode": "한 건씩 검수",
        "review_status_view": "검수 대기",
        "review_index": 0,
        "review_confirm": None,
        "review_flash": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _set_flash(message: str, *, kind: str = "success") -> None:
    st.session_state["review_flash"] = {"kind": kind, "message": message}


def _clear_confirm() -> None:
    st.session_state["review_confirm"] = None


def _show_flash() -> None:
    flash = st.session_state.get("review_flash")
    if not flash:
        return
    kind = flash.get("kind") or "success"
    message = flash.get("message") or ""
    if kind == "error":
        st.error(message)
    else:
        st.success(message)
    st.session_state["review_flash"] = None


def _approve(
    candidate: dict[str, Any],
    instrument_key: str,
    alias: str,
) -> bool:
    alias = (alias or "").strip()
    if not alias:
        _set_flash("등록할 라벨이 비어 있습니다.", kind="error")
        return False
    if not instrument_key:
        _set_flash("등록할 상품을 선택하세요.", kind="error")
        return False

    try:
        backup_path = add_alias(instrument_key, alias)
    except YamlServiceError as exc:
        title, detail = friendly_yaml_error(exc)
        _set_flash(f"{title}\n{detail}", kind="error")
        return False

    updated = set_candidate_status(candidate["id"], "approved")
    if updated is None:
        _set_flash("후보 상태를 갱신하지 못했습니다.", kind="error")
        return False

    top = top_suggestions(candidate.get("suggestions") or [], limit=1)
    add_review_history(
        candidate_id=candidate["id"],
        action="approve",
        instrument_key=instrument_key,
        alias=alias,
        previous_value=None,
        new_value=alias,
        backup_path=str(backup_path),
        meta_json={
            "top_suggestion": top[0] if top else None,
            "suggestions": candidate.get("suggestions") or [],
        },
    )
    product = display_name_for(instrument_key)
    _set_flash(f"“{alias}”이(가) {product}에 등록되었습니다.")
    return True


def _ignore(candidate: dict[str, Any]) -> bool:
    set_candidate_status(candidate["id"], "ignored")
    add_review_history(
        candidate_id=candidate["id"],
        action="ignore",
        alias=candidate.get("raw_label"),
    )
    label = candidate.get("raw_label") or ""
    _set_flash(f"“{label}”을(를) 제외 목록으로 이동했습니다.")
    return True


def _unignore(candidate: dict[str, Any]) -> bool:
    set_candidate_status(candidate["id"], "pending")
    add_review_history(
        candidate_id=candidate["id"],
        action="unignore",
        alias=candidate.get("raw_label"),
    )
    label = candidate.get("raw_label") or ""
    _set_flash(f"“{label}”을(를) 다시 검수 대기로 옮겼습니다.")
    return True


def _render_confirm(
    candidates: list[dict[str, Any]],
) -> None:
    confirm = st.session_state.get("review_confirm")
    if not confirm:
        return

    action = confirm.get("action")
    candidate_id = confirm.get("candidate_id")
    candidate = next(
        (item for item in candidates if item.get("id") == candidate_id),
        None,
    )
    if candidate is None:
        _clear_confirm()
        return

    current_index = st.session_state.get("review_index", 0)

    if action == "approve":
        product = display_name_for(confirm.get("instrument_key"))
        alias = confirm.get("alias") or ""
        st.markdown(
            confirm_box(
                "다음과 같이 등록합니다.",
                [f"상품: {product}", f"추가 라벨: {alias}"],
            ),
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("등록 확인", type="primary", key="confirm_approve"):
                ok = _approve(
                    candidate,
                    confirm.get("instrument_key") or "",
                    alias,
                )
                _clear_confirm()
                if ok:
                    remaining = max(len(candidates) - 1, 0)
                    st.session_state["review_index"] = next_index_after_remove(
                        current_index,
                        remaining,
                    )
                st.rerun()
        with col2:
            if st.button("취소", key="cancel_approve"):
                _clear_confirm()
                st.rerun()
        return

    if action == "ignore":
        label = candidate.get("raw_label") or ""
        st.markdown(
            confirm_box(
                "이 라벨을 앞으로 검수 목록에서 제외할까요?",
                [f"제외 라벨: {label}"],
            ),
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("제외 확인", key="confirm_ignore"):
                ok = _ignore(candidate)
                _clear_confirm()
                if ok:
                    remaining = max(len(candidates) - 1, 0)
                    st.session_state["review_index"] = next_index_after_remove(
                        current_index,
                        remaining,
                    )
                st.rerun()
        with col2:
            if st.button("취소", key="cancel_ignore"):
                _clear_confirm()
                st.rerun()


def _render_suggestions(suggestions: list[dict[str, Any]]) -> None:
    ranked = top_suggestions(suggestions, limit=3)
    if not ranked:
        st.caption("추천 상품이 없습니다. 아래에서 직접 상품을 선택하세요.")
        return
    for index, item in enumerate(ranked, start=1):
        key = item.get("instrument_key") or ""
        score = item.get("score")
        st.markdown(
            suggestion_card(
                rank=index,
                display_name=display_name_for(key),
                score=None if score is None else float(score),
                strength=recommendation_strength(score),
                top=index == 1,
            ),
            unsafe_allow_html=True,
        )


def _render_one_candidate(
    candidate: dict[str, Any],
    *,
    index: int,
    pending: list[dict[str, Any]],
) -> None:
    total = len(pending)
    st.markdown(
        progress_bar(index + 1, total),
        unsafe_allow_html=True,
    )
    st.markdown(
        label_hero(candidate.get("raw_label") or "-"),
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.15, 1])
    with left:
        st.markdown("#### 발견 정보")
        rating = candidate.get("rating") or "-"
        outlook = candidate.get("outlook") or "-"
        st.markdown(
            meta_grid(
                [
                    ("회사명", candidate.get("company_name") or "-"),
                    ("신평사", candidate.get("agency") or "-"),
                    ("등급", f"{rating} / {outlook}"),
                    ("평가 종류", candidate.get("evaluation_type") or "-"),
                ]
            ),
            unsafe_allow_html=True,
        )
        st.markdown("**원본 문장**")
        st.write(candidate.get("label_text") or "-")

        with st.expander("원본 추출 정보 보기"):
            st.write(f"**파일명:** {candidate.get('file_name') or '-'}")
            st.write(f"**원본 행:** {candidate.get('label_text') or '-'}")
            st.write(
                f"**정규화 라벨:** {candidate.get('normalized_label') or '-'}"
            )
            st.write(
                f"**발견 시각:** "
                f"{format_datetime(candidate.get('last_seen_at'))}"
            )
            st.write(
                f"**발견 횟수:** {candidate.get('occurrence_count') or 0}회"
            )
            reasons = []
            for item in top_suggestions(candidate.get("suggestions") or []):
                for reason in item.get("reasons") or []:
                    reasons.append(reason)
            if reasons:
                st.write("**추천 근거**")
                for reason in reasons:
                    st.caption(f"- {reason}")

    with right:
        st.markdown("#### 검수 및 등록")
        st.markdown("**추천 상품**")
        _render_suggestions(candidate.get("suggestions") or [])

        options = instrument_options()
        option_keys = [key for key, _ in options]
        option_labels = {key: label for key, label in options}
        default_key = default_instrument_key(
            candidate.get("suggestions") or []
        )
        default_index = (
            option_keys.index(default_key)
            if default_key in option_keys
            else 0
        )
        selected_key = st.selectbox(
            "등록할 상품",
            option_keys,
            index=default_index if option_keys else 0,
            format_func=lambda key: option_labels.get(key, key),
            key=f"review_instrument_{candidate['id']}",
        )
        alias = st.text_input(
            "등록할 라벨",
            value=candidate.get("raw_label") or "",
            key=f"review_alias_{candidate['id']}",
        )

        st.caption("이 상품으로 등록 → 선택한 상품의 등록 라벨에 추가됩니다.")
        st.caption(
            "상품 라벨 아님 → 앞으로 동일한 라벨은 검수 목록에 표시하지 않습니다."
        )

        btn1, btn2, btn3 = st.columns(3)
        with btn1:
            if st.button(
                "이 상품으로 등록",
                type="primary",
                key=f"ask_approve_{candidate['id']}",
            ):
                st.session_state["review_confirm"] = {
                    "action": "approve",
                    "candidate_id": candidate["id"],
                    "instrument_key": selected_key,
                    "alias": alias,
                }
                st.rerun()
        with btn2:
            if st.button(
                "상품 라벨 아님",
                key=f"ask_ignore_{candidate['id']}",
            ):
                st.session_state["review_confirm"] = {
                    "action": "ignore",
                    "candidate_id": candidate["id"],
                }
                st.rerun()
        with btn3:
            if st.button("다음에 검수", key=f"skip_{candidate['id']}"):
                st.session_state["review_index"] = clamp_index(
                    index + 1,
                    total,
                )
                _clear_confirm()
                st.rerun()

    _render_confirm(pending)

    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button("이전 항목", disabled=index <= 0, key="review_prev"):
            st.session_state["review_index"] = index - 1
            _clear_confirm()
            st.rerun()
    with nav2:
        if st.button(
            "다음 항목",
            disabled=index >= total - 1,
            key="review_next",
        ):
            st.session_state["review_index"] = index + 1
            _clear_confirm()
            st.rerun()


def _render_pending_list(candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        st.info("검수 대기 라벨이 없습니다.")
        return
    rows = []
    for item in candidates:
        rows.append(
            {
                "발견된 라벨": item.get("raw_label"),
                "회사명": item.get("company_name"),
                "신평사": item.get("agency"),
                "등급": item.get("rating"),
                "발견 횟수": item.get("occurrence_count"),
                "최근 발견": format_datetime(item.get("last_seen_at")),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("실제 등록·제외는 ‘한 건씩 검수’ 화면에서 진행하세요.")


def _render_ignored(candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        st.info("제외된 라벨이 없습니다.")
        return
    for candidate in candidates:
        st.markdown("---")
        st.markdown(
            badge("ignored")
            + f" **{candidate.get('raw_label') or '-'}**",
            unsafe_allow_html=True,
        )
        st.caption(
            f"제외일: {format_datetime(candidate.get('reviewed_at'))} · "
            f"발견 {candidate.get('occurrence_count') or 0}회"
        )
        if st.button(
            "다시 검수하기",
            key=f"unignore_{candidate['id']}",
        ):
            if _unignore(candidate):
                st.session_state["review_status_view"] = "검수 대기"
                st.session_state["review_index"] = 0
                st.rerun()


def render_review_tab(
    *,
    agency: str = "전체",
    company_query: str = "",
    period: str = "전체",
) -> None:
    _init_review_state()
    _show_flash()

    pending_all = list_pending()
    ignored_all = list_ignored()
    pending = filter_candidates(
        pending_all,
        agency=agency,
        company_query=company_query,
        period=period,
    )
    ignored = filter_candidates(
        ignored_all,
        agency=agency,
        company_query=company_query,
        period=period,
    )

    status_cols = st.columns(2)
    with status_cols[0]:
        if st.button(
            f"검수 대기 {len(pending)}",
            use_container_width=True,
            type=(
                "primary"
                if st.session_state["review_status_view"] == "검수 대기"
                else "secondary"
            ),
            key="status_pending_btn",
        ):
            st.session_state["review_status_view"] = "검수 대기"
            st.session_state["review_index"] = 0
            _clear_confirm()
            st.rerun()
    with status_cols[1]:
        if st.button(
            f"제외됨 {len(ignored)}",
            use_container_width=True,
            type=(
                "primary"
                if st.session_state["review_status_view"] == "제외됨"
                else "secondary"
            ),
            key="status_ignored_btn",
        ):
            st.session_state["review_status_view"] = "제외됨"
            _clear_confirm()
            st.rerun()

    if st.session_state["review_status_view"] == "제외됨":
        _render_ignored(ignored)
        return

    mode_cols = st.columns(2)
    with mode_cols[0]:
        if st.button(
            "한 건씩 검수",
            use_container_width=True,
            type=(
                "primary"
                if st.session_state["review_mode"] == "한 건씩 검수"
                else "secondary"
            ),
            key="mode_one_btn",
        ):
            st.session_state["review_mode"] = "한 건씩 검수"
            st.rerun()
    with mode_cols[1]:
        if st.button(
            "전체 목록 보기",
            use_container_width=True,
            type=(
                "primary"
                if st.session_state["review_mode"] == "전체 목록 보기"
                else "secondary"
            ),
            key="mode_list_btn",
        ):
            st.session_state["review_mode"] = "전체 목록 보기"
            st.rerun()

    if not pending:
        st.info("검수 대기 중인 라벨이 없습니다.")
        return

    if st.session_state["review_mode"] == "전체 목록 보기":
        _render_pending_list(pending)
        return

    index = clamp_index(st.session_state.get("review_index", 0), len(pending))
    st.session_state["review_index"] = index
    _render_one_candidate(
        pending[index],
        index=index,
        pending=pending,
    )
