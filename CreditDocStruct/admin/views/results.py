"""결과 조회 화면."""

from __future__ import annotations

import streamlit as st

from admin.services.result_service import (
    ResultServiceError,
    build_public_excel_bytes,
    build_public_rows,
    filter_results,
    list_result_files,
    load_results_json,
    summarize_results,
)
from common.settings import get_instruments_config
from export.excel import EXCEL_PUBLIC_COLUMNS


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
        status = st.selectbox(
            "처리상태", ["전체", "success", "partial", "fail"]
        )
    with filters[1]:
        query = st.text_input("회사명 검색")

    filtered = filter_results(
        results,
        status=status,
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
    rows = build_public_rows(filtered, config)
    table = [
        {key: row.get(key, "") for key in EXCEL_PUBLIC_COLUMNS}
        for row in rows
    ]
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Excel 다운로드",
        data=build_public_excel_bytes(filtered, config),
        file_name=f"{selected.path.stem}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )
