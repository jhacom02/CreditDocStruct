"""기업용 Streamlit 테마·배지·카드 HTML 헬퍼."""

from __future__ import annotations

import html
from typing import Any


STATUS_COLORS = {
    "pending": ("#fff7ed", "#c2410c", "검수 대기"),
    "approved": ("#ecfdf5", "#047857", "승인 완료"),
    "ignored": ("#f3f4f6", "#4b5563", "제외됨"),
    "error": ("#fef2f2", "#b91c1c", "오류"),
    "success": ("#ecfdf5", "#047857", "성공"),
    "fail": ("#fef2f2", "#b91c1c", "실패"),
    "recommend": ("#eff6ff", "#1d4ed8", "추천 1순위"),
}


def escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


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
    h1, h2, h3 {
        color: #1a3c6e;
        letter-spacing: -0.01em;
    }
    .crf-subtitle {
        color: #4b5563;
        margin: -0.4rem 0 1.2rem 0;
        font-size: 0.98rem;
    }
    .crf-kpi-row {
        display: flex;
        gap: 0.75rem;
        margin-bottom: 0.85rem;
    }
    .crf-kpi {
        flex: 1 1 0;
        min-width: 0;
        background: #f8fafc;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 0.85rem 1rem;
        text-align: center;
    }
    .crf-kpi .label {
        color: #6b7280;
        font-size: 0.82rem;
        margin-bottom: 0.25rem;
    }
    .crf-kpi .value {
        color: #1a3c6e;
        font-size: 1.45rem;
        font-weight: 700;
    }
    .crf-badge {
        display: inline-block;
        border-radius: 999px;
        padding: 0.18rem 0.65rem;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 0.35rem;
    }
    .crf-label-card {
        background: #ffffff;
        border: 1px solid #dbe3ef;
        border-left: 5px solid #1a3c6e;
        border-radius: 12px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 0.9rem;
        box-shadow: 0 1px 2px rgba(26, 60, 110, 0.04);
    }
    .crf-label-card .title {
        color: #6b7280;
        font-size: 0.85rem;
        margin-bottom: 0.35rem;
    }
    .crf-label-card .value {
        color: #111827;
        font-size: 1.7rem;
        font-weight: 700;
        line-height: 1.3;
        word-break: break-word;
    }
    .crf-progress-wrap {
        margin: 0.4rem 0 1rem 0;
    }
    .crf-progress-label {
        color: #4b5563;
        font-size: 0.9rem;
        margin-bottom: 0.35rem;
    }
    .crf-progress-bar {
        width: 100%;
        height: 10px;
        background: #e5e7eb;
        border-radius: 999px;
        overflow: hidden;
    }
    .crf-progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #1a3c6e, #3b82f6);
        border-radius: 999px;
    }
    .crf-meta-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.55rem 1rem;
        margin: 0.7rem 0;
    }
    .crf-meta-item .k {
        color: #6b7280;
        font-size: 0.8rem;
    }
    .crf-meta-item .v {
        color: #111827;
        font-weight: 600;
        word-break: break-word;
    }
    .crf-suggest {
        background: #f8fafc;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 0.7rem 0.85rem;
        margin-bottom: 0.45rem;
    }
    .crf-suggest.top {
        border-color: #93c5fd;
        background: #eff6ff;
    }
    .crf-suggest .rank {
        font-size: 0.78rem;
        color: #1d4ed8;
        font-weight: 700;
    }
    .crf-suggest .name {
        font-weight: 700;
        color: #111827;
        margin: 0.15rem 0;
    }
    .crf-suggest .score {
        color: #4b5563;
        font-size: 0.85rem;
    }
    .crf-history-card {
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.65rem;
        background: #ffffff;
    }
    .crf-history-card.system {
        opacity: 0.78;
        background: #f9fafb;
    }
    .crf-history-card .when {
        color: #6b7280;
        font-size: 0.82rem;
    }
    .crf-history-card .sentence {
        color: #111827;
        font-weight: 600;
        margin: 0.25rem 0;
    }
    .crf-confirm {
        border: 1px solid #fcd34d;
        background: #fffbeb;
        border-radius: 10px;
        padding: 0.9rem 1rem;
        margin: 0.7rem 0;
    }
    .crf-doc-summary {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.5rem 1.5rem;
        margin: 0.3rem 0 1rem 0;
    }
    .crf-doc-summary .item {
        display: flex;
        align-items: baseline;
        gap: 0.45rem;
    }
    .crf-doc-summary .k {
        color: #6b7280;
        font-size: 0.8rem;
    }
    .crf-doc-summary .v {
        color: #111827;
        font-weight: 700;
    }
    /* Streamlit 위젯 레이블(예: selectbox)과 동일한 서식 위계 */
    .crf-subhead {
        color: #31333f;
        font-size: 0.875rem;
        font-weight: 400;
        margin: 0.3rem 0 0.35rem 0;
    }
    .crf-rating-rows {
        margin-bottom: 0.8rem;
    }
    .crf-rating-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        padding: 0.32rem 0;
        border-bottom: 1px solid #f1f5f9;
        font-size: 0.92rem;
    }
    .crf-rating-row .name {
        color: #111827;
        min-width: 0;
    }
    .crf-rating-row .grade {
        color: #1a3c6e;
        font-weight: 600;
        white-space: nowrap;
    }
    .crf-eval-badge {
        display: inline-block;
        background: #eef2f7;
        color: #3b556e;
        border-radius: 999px;
        font-size: 0.72rem;
        padding: 0.05rem 0.5rem;
        margin-left: 0.35rem;
        vertical-align: middle;
    }
</style>
        """,
        unsafe_allow_html=True,
    )


def badge(kind: str, text: str | None = None) -> str:
    bg, fg, default = STATUS_COLORS.get(kind, ("#f3f4f6", "#374151", kind))
    label = escape(text or default)
    return (
        f'<span class="crf-badge" style="background:{bg};color:{fg};">'
        f"{label}</span>"
    )


def kpi_row(items: list[tuple[str, Any]]) -> str:
    cells = []
    for label, value in items:
        cells.append(
            "<div class='crf-kpi'>"
            f"<div class='label'>{escape(label)}</div>"
            f"<div class='value'>{escape(value)}</div>"
            "</div>"
        )
    return f"<div class='crf-kpi-row'>{''.join(cells)}</div>"


def label_hero(raw_label: str) -> str:
    return (
        "<div class='crf-label-card'>"
        "<div class='title'>발견된 라벨</div>"
        f"<div class='value'>{escape(raw_label) or '-'}</div>"
        "</div>"
    )


def progress_bar(current: int, total: int) -> str:
    total = max(total, 0)
    current = max(min(current, total if total else 0), 0)
    pct = 0.0 if total == 0 else (current / total) * 100.0
    return (
        "<div class='crf-progress-wrap'>"
        f"<div class='crf-progress-label'>검수 대기 {escape(current)} / "
        f"{escape(total)} · {pct:.0f}%</div>"
        "<div class='crf-progress-bar'>"
        f"<div class='crf-progress-fill' style='width:{pct:.1f}%;'></div>"
        "</div></div>"
    )


def meta_grid(pairs: list[tuple[str, Any]]) -> str:
    cells = []
    for key, value in pairs:
        cells.append(
            "<div class='crf-meta-item'>"
            f"<div class='k'>{escape(key)}</div>"
            f"<div class='v'>{escape(value) or '-'}</div>"
            "</div>"
        )
    return f"<div class='crf-meta-grid'>{''.join(cells)}</div>"


def suggestion_card(
    *,
    rank: int,
    display_name: str,
    score: float | None,
    strength: str,
    top: bool = False,
) -> str:
    score_text = "-" if score is None else f"{float(score):.1f}"
    klass = "crf-suggest top" if top else "crf-suggest"
    badge_html = badge("recommend") if top else ""
    return (
        f"<div class='{klass}'>"
        f"<div class='rank'>{rank}순위 {badge_html}</div>"
        f"<div class='name'>{escape(display_name)}</div>"
        f"<div class='score'>추천 점수 {escape(score_text)} · "
        f"{escape(strength)}</div>"
        "</div>"
    )


def history_card(
    *,
    when: str,
    sentence: str,
    system: bool = False,
) -> str:
    klass = "crf-history-card system" if system else "crf-history-card"
    return (
        f"<div class='{klass}'>"
        f"<div class='when'>{escape(when)}</div>"
        f"<div class='sentence'>{escape(sentence)}</div>"
        "</div>"
    )


def doc_summary(badge_html: str, pairs: list[tuple[str, Any]]) -> str:
    """상태 배지 + 레이블·값 쌍을 한 줄 요약으로 렌더한다."""
    items = [f"<div class='item'>{badge_html}</div>"]
    for key, value in pairs:
        items.append(
            "<div class='item'>"
            f"<span class='k'>{escape(key)}</span>"
            f"<span class='v'>{escape(value) or '-'}</span>"
            "</div>"
        )
    return f"<div class='crf-doc-summary'>{''.join(items)}</div>"


def rating_rows(rows: list[tuple[str, str, str]]) -> str:
    """(상품명, 평가종류, 등급/전망) 목록을 간결한 행으로 렌더한다."""
    cells = []
    for name, eval_type, grade in rows:
        eval_badge = (
            f"<span class='crf-eval-badge'>{escape(eval_type)}</span>"
            if eval_type and eval_type != "-"
            else ""
        )
        cells.append(
            "<div class='crf-rating-row'>"
            f"<div class='name'>{escape(name)}{eval_badge}</div>"
            f"<div class='grade'>{escape(grade)}</div>"
            "</div>"
        )
    return f"<div class='crf-rating-rows'>{''.join(cells)}</div>"


def subhead(text: str) -> str:
    return f"<div class='crf-subhead'>{escape(text)}</div>"


def confirm_box(title: str, lines: list[str]) -> str:
    body = "".join(f"<div>{escape(line)}</div>" for line in lines)
    return (
        "<div class='crf-confirm'>"
        f"<strong>{escape(title)}</strong>{body}"
        "</div>"
    )
