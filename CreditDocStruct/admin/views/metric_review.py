"""재무지표 라벨 검수 화면."""

from __future__ import annotations

import streamlit as st

from admin.services.metric_candidate_store import (
    get_metric_candidate,
    list_metric_candidates,
    set_metric_candidate_status,
)
from admin.services.metrics_yaml_service import (
    MetricsYamlServiceError,
    add_metric_alias,
    list_metric_options,
)
from export.document_store import renormalize_all


def render_metric_review_tab(
    *,
    agency: str = "전체",
    company_query: str = "",
    period: str = "전체",
) -> None:
    del period  # 기간 필터는 라벨 검수와 동일 사이드바 호환용
    candidates = list_metric_candidates(
        status="pending",
        agency=agency,
        company_query=company_query or None,
    )
    if not candidates:
        st.info("대기 중인 재무지표 라벨이 없습니다.")
        return

    options = list_metric_options()
    metric_keys = [key for key, _ in options]
    labels = {key: name for key, name in options}

    st.caption(f"대기 {len(candidates)}건")
    for candidate in candidates:
        with st.container(border=True):
            st.markdown(f"**{candidate['raw_label']}**")
            st.caption(
                f"{candidate.get('company_name') or '-'} · "
                f"{candidate.get('agency') or '-'} · "
                f"출현 {candidate.get('occurrence_count', 1)}회 · "
                f"{candidate.get('file_name') or ''}"
            )
            cols = st.columns([2, 1, 1, 1])
            with cols[0]:
                selected = st.selectbox(
                    "표준 지표",
                    metric_keys,
                    key=f"metric_key_{candidate['id']}",
                    format_func=lambda key: f"{labels.get(key, key)} ({key})",
                )
            with cols[1]:
                if st.button("승인", key=f"approve_metric_{candidate['id']}"):
                    try:
                        add_metric_alias(selected, candidate["raw_label"])
                        set_metric_candidate_status(
                            int(candidate["id"]), "approved"
                        )
                        with st.spinner("재무지표 재정규화 중..."):
                            stats = renormalize_all()
                        st.success(
                            "승인·재정규화 완료 "
                            f"(문서 {stats['documents']}, "
                            f"facts {stats['facts']})"
                        )
                        st.rerun()
                    except MetricsYamlServiceError as exc:
                        st.error(str(exc))
            with cols[2]:
                if st.button("제외", key=f"ignore_metric_{candidate['id']}"):
                    set_metric_candidate_status(
                        int(candidate["id"]), "ignored"
                    )
                    st.rerun()
            with cols[3]:
                detail = get_metric_candidate(int(candidate["id"]))
                if detail:
                    st.caption(detail.get("normalized_label") or "")
