"""확인 필요 — 결과 JSON 예외 대기열 (읽기 전용)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from admin.services.exception_service import collect_exceptions
from admin.services.result_service import (
    ResultServiceError,
    list_result_files,
    load_results_json,
)


def _section_label(text: str) -> None:
    st.markdown(
        f'<p class="section-label">{text}</p>',
        unsafe_allow_html=True,
    )


def render_exceptions_tab() -> None:
    files = list_result_files()
    if not files:
        st.info(
            "결과 파일이 없습니다. `main.py`로 PDF 추출을 실행하면 "
            "`results/` 폴더에 JSON이 생성됩니다."
        )
        return

    names = [item.name for item in files]
    selected_name = st.selectbox("결과 파일", names, key="exc_result_file")
    selected = next(item for item in files if item.name == selected_name)
    try:
        results = load_results_json(selected.path)
    except ResultServiceError as exc:
        st.error(str(exc))
        return

    items = collect_exceptions(results)
    st.caption(f"확인 필요 {len(items)}건")

    if not items:
        st.success("선택한 결과에서 확인이 필요한 항목이 없습니다.")
        return

    by_type: dict[str, list[dict]] = {}
    for item in items:
        by_type.setdefault(item["type_label"], []).append(item)

    for type_label, group in by_type.items():
        _section_label(f"{type_label} ({len(group)})")
        action = group[0].get("action") or ""
        if action:
            st.caption(action)

        rows = []
        for item in group:
            rows.append(
                {
                    "No": item.get("result_no"),
                    "회사명": item.get("company_name"),
                    "신평사": item.get("agency"),
                    "원본파일명": item.get("file_name"),
                    "상세": item.get("detail") or item.get("message") or "",
                }
            )
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
        )
