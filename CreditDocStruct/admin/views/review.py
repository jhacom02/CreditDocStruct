"""라벨 검수 — 3열(라벨·상품선택·승인/거절)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from admin.services.candidate_store import list_pending, set_candidate_status
from admin.services.yaml_service import YamlServiceError, add_alias
from admin.ui.copy import (
    default_instrument_key,
    display_name_for,
    friendly_yaml_error,
    instrument_options,
    top_suggestions,
)


def _approve(candidate: dict[str, Any], instrument_key: str) -> bool:
    alias = (candidate.get("raw_label") or "").strip()
    if not alias:
        st.error("등록할 라벨이 비어 있습니다.")
        return False
    if not instrument_key:
        st.error("등록할 상품을 선택하세요.")
        return False

    try:
        add_alias(instrument_key, alias)
    except YamlServiceError as exc:
        title, detail = friendly_yaml_error(exc)
        st.error(f"{title}\n{detail}")
        return False

    updated = set_candidate_status(candidate["id"], "approved")
    if updated is None:
        st.error("후보 상태를 갱신하지 못했습니다.")
        return False

    product = display_name_for(instrument_key)
    st.toast(f"“{alias}” → {product} 등록")
    return True


def _reject(candidate: dict[str, Any]) -> bool:
    set_candidate_status(candidate["id"], "ignored")
    label = candidate.get("raw_label") or ""
    st.toast(f"“{label}” 제외")
    return True


def render_review_tab() -> None:
    pending = list_pending()
    if not pending:
        st.info("검수 대기 중인 라벨이 없습니다.")
        return

    options = instrument_options()
    option_keys = [key for key, _ in options]
    option_labels = {key: label for key, label in options}

    header1, header2, header3 = st.columns([3, 3, 2])
    header1.markdown("**라벨**")
    header2.markdown("**상품선택**")
    header3.markdown("**승인/거절**")

    for candidate in pending:
        candidate_id = candidate["id"]
        col1, col2, col3 = st.columns([3, 3, 2])

        with col1:
            st.write(candidate.get("raw_label") or "-")

        with col2:
            default_key = default_instrument_key(
                candidate.get("suggestions") or []
            )
            default_index = (
                option_keys.index(default_key)
                if default_key in option_keys
                else 0
            )
            selected_key = st.selectbox(
                "상품",
                option_keys,
                index=default_index if option_keys else 0,
                format_func=lambda key: option_labels.get(key, key),
                key=f"instrument_{candidate_id}",
                label_visibility="collapsed",
            )
            top = top_suggestions(candidate.get("suggestions") or [], limit=1)
            if top:
                suggest_key = top[0].get("instrument_key")
                if suggest_key:
                    st.caption(
                        f"추천: {display_name_for(suggest_key)}"
                    )

        with col3:
            btn_approve, btn_reject = st.columns(2)
            with btn_approve:
                if st.button(
                    "승인",
                    key=f"approve_{candidate_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    if _approve(candidate, selected_key):
                        st.rerun()
            with btn_reject:
                if st.button(
                    "거절",
                    key=f"reject_{candidate_id}",
                    use_container_width=True,
                ):
                    if _reject(candidate):
                        st.rerun()

        st.divider()
