"""Streamlit 최소 스타일."""

from __future__ import annotations


def inject_styles() -> None:
    import streamlit as st

    st.markdown(
        """
<style>
    /* 본문 여백·최대 너비 */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* 섹션 제목 (신용등급·주요 재무지표·상품분류 등) */
    .section-label {
        font-size: 0.85rem;
        font-weight: 400;
        line-height: 1.6;
        color: rgba(49, 51, 63, 0.8);
        margin: 0.5rem 0 0.25rem 0;
        letter-spacing: normal;
    }

    /* st.error / st.warning 박스 본문 */
    div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
        font-size: 0.85rem !important;
    }

    /* Excel 다운로드 버튼 */
    div[data-testid="stDownloadButton"] > button {
        background-color: #dff3e4 !important;
        border-color: #b7e4c7 !important;
        color: #2e7d32 !important;
    }

    div[data-testid="stDownloadButton"] > button:hover {
        background-color: #d7f2dc !important;
        border-color: #a8ddb8 !important;
        color: #1b5e20 !important;
    }

    div[data-testid="stDownloadButton"] > button:active {
        background-color: #c7ebd0 !important;
        border-color: #95d5b2 !important;
        color: #145a1f !important;
        box-shadow: none !important;
    }

    /* 상품 사전 추가 버튼 */
    div[class*="st-key-dict_confirm_"] button {
        background-color: #dff3e4 !important;
        border-color: #b7e4c7 !important;
        color: #2e7d32 !important;
    }

    div[class*="st-key-dict_confirm_"] button:hover {
        background-color: #d7f2dc !important;
        border-color: #a8ddb8 !important;
        color: #1b5e20 !important;
    }

    div[class*="st-key-dict_confirm_"] button:active {
        background-color: #c7ebd0 !important;
        border-color: #95d5b2 !important;
        color: #145a1f !important;
        box-shadow: none !important;
    }

    /* 상품 사전 삭제 버튼 */
    div[class*="st-key-dict_delete_"] button {
        background-color: #fbe4e6 !important;
        border-color: #f2b8bd !important;
        color: #b3261e !important;
    }

    div[class*="st-key-dict_delete_"] button:hover {
        background-color: #f8d6d9 !important;
        border-color: #e8a4aa !important;
        color: #8c1d18 !important;
    }

    div[class*="st-key-dict_delete_"] button:active {
        background-color: #f2c5c9 !important;
        border-color: #dc8f96 !important;
        color: #741612 !important;
        box-shadow: none !important;
    }
</style>
        """,
        unsafe_allow_html=True,
    )
