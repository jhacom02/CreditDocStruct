"""Streamlit 관리자 애플리케이션."""

from __future__ import annotations

import streamlit as st

from admin.services.candidate_store import (
    count_by_status,
    reconcile_candidate_statuses,
)
from admin.services.yaml_service import load_active_alias_lookup
from admin.ui.theme import inject_styles
from admin.views.results import render_result_tab
from admin.views.review import render_review_tab


@st.cache_resource(show_spinner=False)
def synchronize_candidates_on_server_start() -> dict[str, int]:
    """Streamlit 서버 프로세스에서 최초 1회 후보 상태를 YAML과 맞춘다."""
    return reconcile_candidate_statuses(load_active_alias_lookup())


def _render_sidebar() -> None:
    if st.sidebar.button("⟲ 새로고침", use_container_width=True):
        st.rerun()
    pending = count_by_status().get("pending", 0)
    st.sidebar.caption(f"검수 대기 {pending}건")


def main() -> None:
    st.set_page_config(
        page_title="CreditDocStruct Admin",
        layout="wide",
    )
    inject_styles()
    synchronize_candidates_on_server_start()

    st.title("관리자 페이지")
    st.caption("추출 결과 확인 · 미분류 라벨 검수")

    _render_sidebar()

    tab1, tab2 = st.tabs(["결과 조회", "라벨 검수"])
    with tab1:
        render_result_tab()
    with tab2:
        render_review_tab()


if __name__ == "__main__":
    main()
