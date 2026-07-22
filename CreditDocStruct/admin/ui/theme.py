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
</style>
        """,
        unsafe_allow_html=True,
    )
