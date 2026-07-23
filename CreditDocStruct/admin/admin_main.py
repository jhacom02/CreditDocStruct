"""Streamlit 관리자 애플리케이션."""

from __future__ import annotations

import streamlit as st

from admin.services.exception_service import count_exceptions
from admin.services.result_service import (
    ResultServiceError,
    list_result_files,
    load_results_json,
)
from admin.ui.theme import inject_styles
from admin.views.dictionary import render_dictionary_tab
from admin.views.exceptions import render_exceptions_tab
from admin.views.guide import render_guide_tab
from admin.views.results import render_result_tab


def _sidebar_exception_count() -> int:
    files = list_result_files()
    if not files:
        return 0
    try:
        results = load_results_json(files[0].path)
    except ResultServiceError:
        return 0
    return count_exceptions(results)


def _render_sidebar() -> None:
    if st.sidebar.button("⟲ 새로고침", use_container_width=True):
        st.rerun()
    pending = _sidebar_exception_count()
    st.sidebar.caption(f"확인 필요 {pending}건")


def main() -> None:
    st.set_page_config(
        page_title="CreditDocStruct Admin",
        layout="wide",
    )
    inject_styles()

    st.title("신용평가서 관리자 페이지")
    st.caption("신평서에서 추출한 신용등급·재무제표를 확인합니다. 비개발자용 유지보수 내역을 관리합니다.")

    _render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs(
        ["결과 조회", "확인 필요", "상품 사전", "운영 가이드"]
    )
    with tab1:
        render_result_tab()
    with tab2:
        render_exceptions_tab()
    with tab3:
        render_dictionary_tab()
    with tab4:
        render_guide_tab()


if __name__ == "__main__":
    main()
