"""결과 조회 화면."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from admin.services.result_service import (
    AGENCY_FILTER_OPTIONS,
    ResultServiceError,
    build_public_excel_bytes,
    build_public_rows_with_sources,
    empty_financial_wide_columns,
    filter_results,
    financial_fail_message,
    financial_table_to_wide_rows,
    first_financial_table,
    list_result_files,
    load_results_json,
    summarize_results,
)
from common.settings import get_instruments_config
from export.excel import EXCEL_PUBLIC_COLUMNS


def _section_label(text: str) -> None:
    st.markdown(
        f'<p class="section-label">{text}</p>',
        unsafe_allow_html=True,
    )


def _empty_financial_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=empty_financial_wide_columns())


def render_result_tab() -> None:
    files = list_result_files()
    if not files:
        st.info(
            "결과 파일이 없습니다. `main.py`로 PDF 추출을 실행하면 "
            "`results/` 폴더에 JSON이 생성됩니다."
        )
        return

    names = [item.name for item in files]
    selected_name = st.selectbox("결과 파일", names)
    selected = next(item for item in files if item.name == selected_name)
    try:
        results = load_results_json(selected.path)
    except ResultServiceError as exc:
        st.error(str(exc))
        return

    if not results:
        st.warning("선택한 결과 파일이 비어 있습니다.")
        return

    filters = st.columns(2)
    with filters[0]:
        agency = st.selectbox("신평사", list(AGENCY_FILTER_OPTIONS))
    with filters[1]:
        query = st.text_input("회사명 검색")

    filtered = filter_results(
        results,
        agency=agency,
        query=query,
    )

    summary = summarize_results(filtered)
    st.caption(
        f"전체 {summary['total']}건 · 성공 {summary['success']} · "
        f"부분성공 {summary['partial']} · 실패 {summary['fail']}"
    )

    if not filtered:
        st.info("필터 조건에 맞는 결과가 없습니다.")
        return

    config = get_instruments_config()
    row_sources = build_public_rows_with_sources(filtered, config)
    table = [
        {key: pair.row.get(key, "") for key in EXCEL_PUBLIC_COLUMNS}
        for pair in row_sources
    ]

    st.download_button(
        "⭳ Excel 다운로드",
        data=build_public_excel_bytes(filtered, config),
        file_name=f"{selected.path.stem}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

    _section_label("신용등급")

    event = st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="rating_results_table",
    )

    _section_label("주요 재무지표")
    st.caption("신용등급 표에서 체크박스 선택 시 해당 발행사, 신평사의 주요 재무지표가 표시됩니다.")

    selected_rows: list[int] = []
    if event is not None and getattr(event, "selection", None) is not None:
        selected_rows = list(event.selection.rows or [])

    if not selected_rows:
        st.dataframe(
            _empty_financial_frame(),
            use_container_width=True,
            hide_index=True,
            key="financial_empty_table",
        )
        return

    row_index = int(selected_rows[0])
    if row_index < 0 or row_index >= len(row_sources):
        st.dataframe(
            _empty_financial_frame(),
            use_container_width=True,
            hide_index=True,
            key="financial_oob_table",
        )
        return

    source_result = row_sources[row_index].result
    fin_table = first_financial_table(source_result)
    columns, wide_rows = financial_table_to_wide_rows(fin_table)

    if not wide_rows:
        st.error(financial_fail_message(source_result))
        return

    display = pd.DataFrame(wide_rows, columns=columns)
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        key="financial_selected_table",
    )
