"""운영 가이드 — ops_guide.md 표시 전용."""

from __future__ import annotations

from pathlib import Path

import streamlit as st


def _guide_path() -> Path:
    return Path(__file__).resolve().parent.parent / "content" / "ops_guide.md"


def render_guide_tab() -> None:
    path = _guide_path()
    if not path.exists():
        st.warning("운영 가이드 파일(ops_guide.md)이 없습니다.")
        return
    text = path.read_text(encoding="utf-8")
    st.markdown(text)
