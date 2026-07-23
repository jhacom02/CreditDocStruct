"""Streamlit 최소 스타일."""

from __future__ import annotations


def inject_styles() -> None:
    import streamlit as st

    st.markdown(
        """
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* 탭·위젯 라벨과 동일 계열 */
    .section-label {
        font-size: 0.7rem;
        font-weight: 400;
        line-height: 1.6;
        color: rgba(49, 51, 63, 0.8);
        margin: 0.5rem 0 0.25rem 0;
        letter-spacing: normal;
    }

    .fin-fail-msg {
        color: #9e9e9e;
        font-size: 0.8rem;
        margin: 0.5rem 0 0.1rem 0;
    }

    /* Excel 다운로드 — 연한 초록 */
    div[data-testid="stDownloadButton"] > button {
        background-color: #e8f5e9 !important;
        border-color: #c8e6c9 !important;
        color: #2e7d32 !important;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background-color: #d7f2dc !important;
        border-color: #b7e4c7 !important;
        color: #1b5e20 !important;
    }
    div[data-testid="stDownloadButton"] > button:active {
        box-shadow: 0 0 0 0.2rem rgba(200, 230, 201, 0.45) !important;
    }

    /* 상품 사전: 추가(연초록) / 삭제(연빨강) */
    div[data-testid="column"]:has(#dict-confirm-marker) button {
        background-color: #c8e6c9 !important;
        border-color: #a5d6a7 !important;
        color: #1b5e20 !important;
    }
    div[data-testid="column"]:has(#dict-confirm-marker) button:hover {
        background-color: #a5d6a7 !important;
        border-color: #81c784 !important;
        color: #1b5e20 !important;
    }
    div[data-testid="column"]:has(#dict-delete-marker) button {
        background-color: #ffcdd2 !important;
        border-color: #ef9a9a !important;
        color: #b71c1c !important;
    }
    div[data-testid="column"]:has(#dict-delete-marker) button:hover {
        background-color: #ef9a9a !important;
        border-color: #e57373 !important;
        color: #b71c1c !important;
    }
</style>
        """,
        unsafe_allow_html=True,
    )
