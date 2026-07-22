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
from export.excel import ADMIN_COLUMNS


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
        {key: row.get(key, "") for key in ADMIN_COLUMNS}
        for row in rows
    ]
    column_config = {}
    for col_name in ("실패사유", "원본파일명", "원본라벨", "회사명"):
        width = max(
            (_display_width(row.get(col_name)) for row in table),
            default=0,
        )
        column_config[col_name] = st.column_config.TextColumn(
            width=max(120, width + 36),
        )
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
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
        st.markdown("###### PDF별 상세 조회")
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
                ("평가일", item.get("evaluation_date") or "-"),
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

    fin_tables = item.get("financial_tables") or []
    tables = item.get("tables") or []
    if tables:
        st.markdown(subhead("추출 표 (3섹션)"), unsafe_allow_html=True)
        for table in tables:
            st.caption(
                f"[{table.get('section_key')}] "
                f"{table.get('title_raw') or '-'} · "
                f"region={table.get('region_id')} · "
                f"source={table.get('source')}"
            )
            headers = table.get("headers") or []
            rows = table.get("rows") or []
            if headers:
                import pandas as pd

                width = len(headers)
                aligned = [
                    list(row[:width]) + [""] * max(0, width - len(row))
                    for row in rows
                ]
                st.dataframe(
                    pd.DataFrame(aligned, columns=headers),
                    use_container_width=True,
                    hide_index=True,
                )
    elif fin_tables:
        st.markdown(subhead("재무지표 표"), unsafe_allow_html=True)
        for index, table in enumerate(fin_tables):
            st.caption(
                f"{table.get('title_raw') or '주요 재무지표'} · "
                f"source={table.get('source')} · "
                f"basis={table.get('basis') or '-'} · "
                f"{table.get('unit_caption') or ''}"
            )
            headers = table.get("headers") or []
            rows = table.get("rows") or []
            if headers:
                import pandas as pd

                width = len(headers)
                aligned = [
                    list(row[:width]) + [""] * max(0, width - len(row))
                    for row in rows
                ]
                st.dataframe(
                    pd.DataFrame(aligned, columns=headers),
                    use_container_width=True,
                    hide_index=True,
                )

    undefined = item.get("undefined_metrics") or []
    if undefined:
        st.caption(
            "미매핑 지표: "
            + ", ".join(
                str(u.get("raw_label") or u.get("normalized_label"))
                for u in undefined
            )
        )
    facts = [
        f
        for f in (item.get("financial_facts") or [])
        if f.get("classification_status") == "matched"
    ]
    if facts:
        with st.expander("정규화 facts 보기"):
            st.json(facts[:80])
