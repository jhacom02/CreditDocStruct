"""결과 조회 화면."""

from __future__ import annotations

import unicodedata
from typing import Any

import streamlit as st

from admin.services.result_service import (
    ResultServiceError,
    build_excel_bytes,
    build_summary_rows,
    filter_results,
    list_result_files,
    load_results_json,
    result_identity,
    summarize_results,
)
from admin.ui.copy import display_name_for, instrument_options
from admin.ui.theme import badge, doc_summary, kpi_row, rating_rows, subhead
from common.settings import get_instruments_config
from export.excel import EXCEL_COLUMNS


def render_result_tab() -> None:
    files = list_result_files()
    if not files:
        st.info(
            "결과 파일이 없습니다. `main.py`로 PDF 추출을 실행하면 "
            "`result/` 폴더에 JSON이 생성됩니다."
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

    agencies = sorted(
        {
            str(item.get("agency"))
            for item in results
            if item.get("agency")
        }
    )
    instrument_keys = ["전체"] + [key for key, _ in instrument_options()]

    filters = st.columns(4)
    with filters[0]:
        status = st.selectbox(
            "처리상태", ["전체", "success", "partial", "fail"]
        )
    with filters[1]:
        agency = st.selectbox("신평사", ["전체", *agencies])
    with filters[2]:
        instrument_key = st.selectbox(
            "상품 분류",
            instrument_keys,
            format_func=lambda key: (
                "전체" if key == "전체" else display_name_for(key)
            ),
        )
    with filters[3]:
        query = st.text_input("회사명/파일명 검색")

    filtered = filter_results(
        results,
        status=status,
        agency=agency,
        instrument_key=instrument_key,
        query=query,
    )
    summary = summarize_results(filtered)
    st.markdown(
        kpi_row(
            [
                ("전체", summary["total"]),
                ("성공", summary["success"]),
                ("부분성공", summary["partial"]),
                ("실패", summary["fail"]),
            ]
        ),
        unsafe_allow_html=True,
    )

    config = get_instruments_config()
    rows = build_summary_rows(filtered, config)
    table = [
        {key: row.get(key, "") for key in EXCEL_COLUMNS}
        for row in rows
    ]
    failure_width = max(
        (_display_width(row.get("실패사유")) for row in table),
        default=0,
    )
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "실패사유": st.column_config.TextColumn(
                width=max(120, failure_width + 36),
            )
        },
    )

    st.download_button(
        "Excel 다운로드",
        data=build_excel_bytes(filtered, config),
        file_name=f"{selected.path.stem}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

    if not filtered:
        st.info("필터 조건에 맞는 결과가 없습니다.")
        return

    with st.container(border=True):
        st.markdown("###### 상세 조회")
        options = {
            result_identity(item): _document_option_label(item)
            for item in filtered
        }
        selected_id = st.selectbox(
            "PDF 선택",
            list(options.keys()),
            format_func=lambda key: options[key],
        )
        detail = next(
            item for item in filtered if result_identity(item) == selected_id
        )
        _render_detail(detail)


def _document_option_label(item: dict[str, Any], *, limit: int = 44) -> str:
    file_name = item.get("file_name") or "-"
    if len(file_name) > limit:
        file_name = file_name[: limit - 1] + "…"
    return f"No.{item.get('result_no')} · {file_name}"


def _display_width(value: Any) -> int:
    """문자열이 잘리지 않도록 한글·영문의 예상 표시 폭을 계산한다."""
    text = str(value or "")
    return sum(
        14 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 8
        for char in text
    )


def _render_detail(item: dict[str, Any]) -> None:
    status = item.get("status") or "-"
    badge_kind = "success" if status in {"success", "partial"} else "fail"
    st.markdown(
        doc_summary(
            badge(badge_kind, status),
            [
                ("회사명", item.get("company_name") or "-"),
                ("신평사", item.get("agency") or "-"),
            ],
        ),
        unsafe_allow_html=True,
    )

    products = item.get("products") or []
    if products:
        rows = [
            (
                display_name_for(product.get("instrument_key")),
                product.get("evaluation_type") or "-",
                f"{product.get('rating') or '-'} / "
                f"{product.get('outlook') or '-'}",
            )
            for product in products
        ]
        st.markdown(
            subhead("등급 내역") + rating_rows(rows),
            unsafe_allow_html=True,
        )
    else:
        fail = item.get("fail_reason") or {}
        st.markdown(subhead("실패 사유"), unsafe_allow_html=True)
        st.write(fail.get("message") or "상품 등급을 확정하지 못했습니다.")
        if fail.get("code"):
            st.caption(f"코드: {fail.get('code')}")

    warnings = item.get("validation_warnings") or []
    if warnings:
        with st.expander("검증 경고"):
            for warning in warnings:
                st.write(warning)

    records = item.get("records") or []
    if records:
        with st.expander("원본 레코드 보기"):
            st.json(records)
