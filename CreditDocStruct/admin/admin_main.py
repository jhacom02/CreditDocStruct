"""Streamlit 관리자 애플리케이션."""

from __future__ import annotations

import streamlit as st

from admin.services.candidate_store import (
    count_by_status,
    list_distinct_agencies,
    reconcile_candidate_statuses,
)
from admin.views.history import render_history_tab
from admin.views.labels import render_label_tab
from admin.views.metric_review import render_metric_review_tab
from admin.views.results import render_result_tab
from admin.views.review import render_review_tab
from admin.ui.theme import inject_styles, kpi_row
from admin.services.yaml_service import load_active_alias_lookup
from admin.services.metric_candidate_store import count_metric_by_status


@st.cache_resource(show_spinner=False)
def synchronize_candidates_on_server_start() -> dict[str, int]:
    """Streamlit 서버 프로세스에서 최초 1회 후보 상태를 YAML과 맞춘다."""
    return reconcile_candidate_statuses(load_active_alias_lookup())


def _render_sidebar(sync_stats: dict[str, int]) -> tuple[str, str, str]:
    if st.sidebar.button("⟲ 새로고침", use_container_width=True):
        st.rerun()

    counts = count_by_status()
    metric_counts = count_metric_by_status()
    st.sidebar.markdown("### 오늘의 현황")
    st.sidebar.markdown(
        kpi_row(
            [
                ("대기", counts.get("pending", 0)),
                ("승인", counts.get("approved", 0)),
                ("제외", counts.get("ignored", 0)),
            ]
        ),
        unsafe_allow_html=True,
    )
    st.sidebar.caption(
        "재무지표 대기 "
        f"{metric_counts.get('pending', 0)} · "
        f"승인 {metric_counts.get('approved', 0)}"
    )

    st.sidebar.markdown("### 필터")
    agencies = ["전체", *list_distinct_agencies()]
    agency = st.sidebar.selectbox("신평사", agencies)
    company_query = st.sidebar.text_input("회사명", placeholder="검색")
    period = st.sidebar.selectbox(
        "기간",
        ["전체", "오늘", "최근 7일", "최근 30일"],
    )

    with st.sidebar.expander("시스템 정보"):
        st.caption(
            "시작 동기화: "
            f"승인 {sync_stats.get('approved', 0)}, "
            f"재검수 {sync_stats.get('reopened', 0)}, "
            f"연결갱신 {sync_stats.get('reassigned', 0)}, "
            f"이력보완 {sync_stats.get('history_backfilled', 0)}"
        )

    return agency, company_query, period


def main() -> None:
    st.set_page_config(
        page_title="신평서 데이터 구조화 프로젝트",
        layout="wide",
    )
    inject_styles()
    sync_stats = synchronize_candidates_on_server_start()

    st.title("신평서 데이터 구조화 프로젝트")
    st.caption("CreditDocStruct 관리자")
    st.markdown(
        '<p class="crf-subtitle">'
        "신용등급·재무지표 추출 결과를 조회하고 새로운 라벨을 등록합니다."
        "</p>",
        unsafe_allow_html=True,
    )

    agency, company_query, period = _render_sidebar(sync_stats)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["결과 조회", "라벨 검수", "지표 검수", "라벨 조회", "작업 이력"]
    )
    with tab1:
        render_result_tab()
    with tab2:
        render_review_tab(
            agency=agency,
            company_query=company_query,
            period=period,
        )
    with tab3:
        render_metric_review_tab(
            agency=agency,
            company_query=company_query,
            period=period,
        )
    with tab4:
        render_label_tab()
    with tab5:
        render_history_tab()


if __name__ == "__main__":
    main()
