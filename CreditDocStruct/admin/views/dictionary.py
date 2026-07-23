"""상품 사전 — instruments.yaml 라벨 조회·추가·삭제."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from admin.services.yaml_service import (
    MANAGED_BY_ADMIN,
    YamlServiceError,
    add_alias,
    delete_aliases,
    list_instrument_aliases,
)
from admin.ui.copy import friendly_yaml_error

_ALIAS_COLUMNS = ("원문라벨", "메모")
_PX_PER_CHAR = 11
_WIDTH_PAD = 24
_WIDTH_MIN = 48
_WIDTH_MAX = 480


def _section_label(text: str) -> None:
    st.markdown(
        f'<p class="section-label">{text}</p>',
        unsafe_allow_html=True,
    )


def _empty_alias_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_ALIAS_COLUMNS))


def _max_text_len(series: pd.Series, header: str) -> int:
    lengths = [len(header)]
    for value in series.fillna("").astype(str):
        lengths.append(len(value))
    return max(lengths)


def _width_for_len(max_len: int) -> int:
    return max(_WIDTH_MIN, min(_WIDTH_MAX, max_len * _PX_PER_CHAR + _WIDTH_PAD))


def _column_config_for_df(df: pd.DataFrame) -> dict[str, Any]:
    """헤더·셀 텍스트 max_length 기준 열 너비."""
    config: dict[str, Any] = {}
    if df.empty and len(df.columns) == 0:
        return config
    for col in df.columns:
        header = str(col)
        max_len = _max_text_len(df[col], header) if len(df) else len(header)
        width = _width_for_len(max_len)
        if pd.api.types.is_numeric_dtype(df[col]) and len(df) > 0:
            config[col] = st.column_config.NumberColumn(header, width=width)
        else:
            config[col] = st.column_config.TextColumn(header, width=width)
    return config


def _show_dataframe(
    df: pd.DataFrame,
    *,
    key: str,
    selection_mode: str | None = None,
) -> Any:
    kwargs: dict[str, Any] = {
        "hide_index": True,
        "use_container_width": True,
        "key": key,
        "column_config": _column_config_for_df(df),
    }
    if selection_mode is not None:
        kwargs["selection_mode"] = selection_mode
        kwargs["on_select"] = "rerun"
    return st.dataframe(df, **kwargs)


def render_dictionary_tab() -> None:
    groups = list_instrument_aliases()
    if not groups:
        st.warning("등록된 상품 분류가 없습니다.")
        return

    _section_label("상품분류")
    instrument_df = pd.DataFrame(
        [
            {
                "No": index,
                "상품키": group.instrument_key,
                "상품명": group.display_name,
            }
            for index, group in enumerate(groups, start=1)
        ]
    )
    instrument_event = _show_dataframe(
        instrument_df,
        key="dict_instrument_table",
        selection_mode="single-row",
    )

    selected_rows: list[int] = []
    if instrument_event is not None and getattr(
        instrument_event, "selection", None
    ) is not None:
        selected_rows = list(instrument_event.selection.rows or [])

    _section_label("원문라벨")

    if not selected_rows:
        _show_dataframe(_empty_alias_frame(), key="dict_alias_empty")
        return

    selected = groups[int(selected_rows[0])]
    instrument_key = selected.instrument_key

    locked_rows: list[dict[str, str]] = []
    free_labels: list[str] = []
    free_rows: list[dict[str, str]] = []

    for alias in selected.aliases:
        row = {"원문라벨": alias.raw_label, "메모": alias.note}
        if alias.is_admin_managed:
            free_rows.append(row)
            free_labels.append(alias.raw_label)
        else:
            locked_rows.append(row)

    locked_df = pd.DataFrame(locked_rows, columns=list(_ALIAS_COLUMNS))
    free_df = pd.DataFrame(free_rows, columns=list(_ALIAS_COLUMNS))

    if locked_rows:
        st.caption("잠금 (삭제 불가)")
        _show_dataframe(
            locked_df,
            key=f"dict_alias_locked_{instrument_key}",
        )

    free_event = None
    if free_rows:
        st.caption("삭제 가능 (체크 후 삭제)")
        free_event = _show_dataframe(
            free_df,
            key=f"dict_alias_free_{instrument_key}",
            selection_mode="multi-row",
        )
    elif not locked_rows:
        _show_dataframe(
            _empty_alias_frame(),
            key=f"dict_alias_none_{instrument_key}",
        )

    label_key = f"dict_new_label_{instrument_key}"
    note_key = f"dict_new_note_{instrument_key}"
    add_cols = st.columns([1, 1])
    with add_cols[0]:
        new_label = st.text_input(
            "원문 라벨",
            key=label_key,
            placeholder="추가할 원문 표현",
        )
    with add_cols[1]:
        new_note = st.text_input(
            "메모",
            key=note_key,
            placeholder="선택",
        )

    btn_cols = st.columns([6, 1, 1])
    with btn_cols[1]:
        st.markdown(
            '<span id="dict-confirm-marker"></span>',
            unsafe_allow_html=True,
        )
        confirm = st.button(
            "추가",
            key=f"dict_confirm_{instrument_key}",
            use_container_width=True,
        )
    with btn_cols[2]:
        st.markdown(
            '<span id="dict-delete-marker"></span>',
            unsafe_allow_html=True,
        )
        delete = st.button(
            "삭제",
            key=f"dict_delete_{instrument_key}",
            use_container_width=True,
        )

    if confirm:
        cleaned = (new_label or "").strip()
        if not cleaned:
            st.warning("원문 라벨을 입력하세요.")
        else:
            existing = {a.raw_label for a in selected.aliases}
            if cleaned in existing:
                st.warning("이미 목록에 있는 라벨입니다.")
            else:
                try:
                    add_alias(
                        instrument_key,
                        cleaned,
                        note=(new_note or "").strip(),
                        managed_by=MANAGED_BY_ADMIN,
                    )
                except YamlServiceError as exc:
                    title, detail = friendly_yaml_error(exc)
                    st.error(title)
                    st.caption(detail)
                else:
                    st.session_state[label_key] = ""
                    st.session_state[note_key] = ""
                    st.success("상품 사전에 반영했습니다.")
                    st.rerun()

    if delete:
        selected_free: list[int] = []
        if free_event is not None and getattr(
            free_event, "selection", None
        ) is not None:
            selected_free = list(free_event.selection.rows or [])

        if not selected_free:
            st.warning("삭제할 행을 체크하세요.")
            return

        to_remove = [
            free_labels[idx]
            for idx in selected_free
            if 0 <= idx < len(free_labels)
        ]
        if not to_remove:
            st.warning("삭제할 관리자 추가 행을 선택하세요.")
            return

        try:
            delete_aliases(to_remove)
        except YamlServiceError as exc:
            title, detail = friendly_yaml_error(exc)
            st.error(title)
            st.caption(detail)
            return
        st.success("선택한 행을 삭제했습니다.")
        st.rerun()
