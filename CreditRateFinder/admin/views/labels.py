"""라벨 조회 화면."""

from __future__ import annotations

import streamlit as st

from admin.services.candidate_store import (
    add_review_history,
    get_occurrence_count_by_normalized,
    latest_history_by_instrument,
)
from admin.ui.copy import (
    display_name_for,
    format_datetime,
    friendly_yaml_error,
)
from admin.ui.theme import confirm_box
from admin.services.yaml_service import (
    YamlServiceError,
    add_alias,
    list_instrument_aliases,
    remove_alias,
)
from common.text_utils import normalize_label


def _init_label_state() -> None:
    if "label_selected_key" not in st.session_state:
        st.session_state["label_selected_key"] = None
    if "label_delete_confirm" not in st.session_state:
        st.session_state["label_delete_confirm"] = None


def render_label_tab() -> None:
    _init_label_state()
    selected_key = st.session_state.get("label_selected_key")
    if selected_key:
        _render_detail(selected_key)
        return
    _render_summary()


def _render_summary() -> None:
    search = st.text_input(
        "상품 또는 라벨 검색",
        placeholder="예: 무보증사채, COCO, CP",
    )
    query = search.strip().lower()
    instruments = list_instrument_aliases()
    latest_map = latest_history_by_instrument()

    if query:
        instruments = [
            item
            for item in instruments
            if query in item.instrument_key.lower()
            or query in item.display_name.lower()
            or any(query in alias.raw_label.lower() for alias in item.aliases)
        ]

    if not instruments:
        st.info("검색 결과가 없습니다.")
        return

    rows = []
    for item in instruments:
        rows.append(
            {
                "상품 분류": item.display_name,
                "등록 라벨 수": len(item.aliases),
                "최근 변경": format_datetime(
                    latest_map.get(item.instrument_key)
                )
                if latest_map.get(item.instrument_key)
                else "기록 없음",
                "상품 코드": item.instrument_key,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.markdown("#### 상품 상세 열기")
    for item in instruments:
        col1, col2 = st.columns([4, 1])
        col1.write(
            f"**{item.display_name}** · 등록 라벨 {len(item.aliases)}개"
        )
        if col2.button("열기", key=f"open_{item.instrument_key}"):
            st.session_state["label_selected_key"] = item.instrument_key
            st.session_state["label_delete_confirm"] = None
            st.rerun()


def _render_detail(instrument_key: str) -> None:
    instruments = {
        item.instrument_key: item for item in list_instrument_aliases()
    }
    item = instruments.get(instrument_key)
    if item is None:
        st.warning("선택한 상품을 찾을 수 없습니다.")
        if st.button("목록으로"):
            st.session_state["label_selected_key"] = None
            st.rerun()
        return

    if st.button("← 목록으로"):
        st.session_state["label_selected_key"] = None
        st.session_state["label_delete_confirm"] = None
        st.rerun()

    st.subheader(item.display_name)
    with st.expander("상품 코드 보기"):
        st.code(item.instrument_key)

    label_search = st.text_input(
        "등록된 라벨 검색",
        key=f"alias_search_{instrument_key}",
    )
    query = label_search.strip().lower()
    aliases = list(item.aliases)
    if query:
        aliases = [
            alias
            for alias in aliases
            if query in alias.raw_label.lower()
        ]

    st.markdown(f"**등록된 라벨 {len(item.aliases)}개**")
    if not aliases:
        st.info("표시할 등록 라벨이 없습니다.")
    else:
        for alias in aliases:
            count = get_occurrence_count_by_normalized(
                normalize_label(alias.raw_label)
            )
            usage = (
                f"최근 문서에서 {count}회 발견됨"
                if count is not None
                else "사용 기록 없음"
            )
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(alias.raw_label)
                st.caption(usage)
            with col2:
                if st.button(
                    "삭제",
                    key=f"ask_del_{instrument_key}_{alias.raw_label}",
                ):
                    st.session_state["label_delete_confirm"] = {
                        "instrument_key": instrument_key,
                        "alias": alias.raw_label,
                    }
                    st.rerun()

    confirm = st.session_state.get("label_delete_confirm")
    if (
        confirm
        and confirm.get("instrument_key") == instrument_key
    ):
        alias = confirm.get("alias") or ""
        st.markdown(
            confirm_box(
                f"“{alias}”을(를) 삭제할까요?",
                [
                    "이 라벨을 사용하는 문서는 다음 실행부터 "
                    "분류되지 않을 수 있습니다.",
                ],
            ),
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("삭제 확인", key="confirm_delete_alias"):
                try:
                    backup = remove_alias(alias)
                    add_review_history(
                        candidate_id=None,
                        action="delete_alias",
                        instrument_key=instrument_key,
                        alias=alias,
                        previous_value=alias,
                        backup_path=str(backup),
                    )
                    st.session_state["label_delete_confirm"] = None
                    st.success(f"“{alias}” 등록 라벨을 삭제했습니다.")
                    st.rerun()
                except YamlServiceError as exc:
                    title, detail = friendly_yaml_error(exc)
                    st.error(f"{title}\n{detail}")
        with c2:
            if st.button("취소", key="cancel_delete_alias"):
                st.session_state["label_delete_confirm"] = None
                st.rerun()

    st.markdown("#### 새 라벨 추가")
    new_alias = st.text_input(
        "등록할 라벨",
        key=f"new_alias_{instrument_key}",
    )
    if st.button("추가", key=f"add_alias_{instrument_key}"):
        try:
            backup = add_alias(instrument_key, new_alias.strip())
            add_review_history(
                candidate_id=None,
                action="add_alias",
                instrument_key=instrument_key,
                alias=new_alias.strip(),
                new_value=new_alias.strip(),
                backup_path=str(backup),
            )
            st.success(
                f"“{new_alias.strip()}”을(를) "
                f"{display_name_for(instrument_key)}에 등록했습니다."
            )
            st.rerun()
        except YamlServiceError as exc:
            title, detail = friendly_yaml_error(exc)
            st.error(f"{title}\n{detail}")
