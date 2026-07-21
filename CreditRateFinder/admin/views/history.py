"""작업 이력 화면."""

from __future__ import annotations

import streamlit as st

from admin.services.candidate_store import add_review_history, list_review_history
from admin.ui.copy import (
    action_label,
    display_name_for,
    format_datetime,
    friendly_yaml_error,
    history_sentence,
    is_system_action,
)
from admin.ui.theme import confirm_box, history_card
from admin.services.yaml_service import (
    YamlServiceError,
    list_backups,
    restore_from_backup,
)


def render_history_tab() -> None:
    history = list_review_history()
    if not history:
        st.info("작업 이력이 없습니다.")
    else:
        for item in history:
            system = is_system_action(item.get("action"))
            st.markdown(
                history_card(
                    when=format_datetime(item.get("created_at")),
                    sentence=history_sentence(item),
                    system=system,
                ),
                unsafe_allow_html=True,
            )
            with st.expander("변경 내용 보기"):
                st.write(f"**작업 유형:** {action_label(item.get('action'))}")
                st.write(f"**변경한 라벨:** {item.get('alias') or '-'}")
                st.write(
                    f"**상품 분류:** "
                    f"{display_name_for(item.get('instrument_key'))}"
                )
                st.write(f"**변경 전:** {item.get('previous_value') or '-'}")
                st.write(f"**변경 후:** {item.get('new_value') or '-'}")
                backup = item.get("backup_path")
                st.write(
                    f"**백업 파일:** "
                    f"{backup if backup else '생성되지 않음'}"
                )

    st.markdown("---")
    st.subheader("백업 관리")
    backups = list_backups()
    if not backups:
        st.write("백업 파일이 없습니다.")
        return

    backup_names = [item["name"] for item in backups]
    selected_name = st.selectbox("백업 파일", backup_names)
    selected = next(
        item for item in backups if item["name"] == selected_name
    )
    st.caption(f"생성: {format_datetime(selected['modified_at'])}")

    if "restore_confirm" not in st.session_state:
        st.session_state["restore_confirm"] = False

    if st.button("이 백업으로 복원"):
        st.session_state["restore_confirm"] = True

    if st.session_state.get("restore_confirm"):
        st.markdown(
            confirm_box(
                "선택한 백업으로 라벨 사전을 복원할까요?",
                [
                    f"백업 파일: {selected_name}",
                    "현재 등록 라벨 설정이 백업 시점 내용으로 바뀝니다.",
                ],
            ),
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("복원 확인", type="primary"):
                try:
                    current_backup = restore_from_backup(selected["path"])
                    add_review_history(
                        candidate_id=None,
                        action="restore_yaml",
                        previous_value=selected["name"],
                        backup_path=str(current_backup),
                    )
                    st.session_state["restore_confirm"] = False
                    st.success("백업으로 복원했습니다.")
                    st.rerun()
                except YamlServiceError as exc:
                    title, detail = friendly_yaml_error(exc)
                    st.error(f"{title}\n{detail}")
        with c2:
            if st.button("취소", key="cancel_restore"):
                st.session_state["restore_confirm"] = False
                st.rerun()
