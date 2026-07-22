"""candidate_store 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from admin.services.candidate_store import (
    add_review_history,
    count_by_status,
    get_candidate_by_id,
    init_db,
    list_pending,
    list_review_history,
    reconcile_candidate_statuses,
    set_candidate_status,
    upsert_occurrences,
)


def _occurrence(
    normalized: str,
    *,
    occurrence_id: str | None = None,
    raw_label: str | None = None,
) -> dict:
    return {
        "occurrence_id": occurrence_id or f"hash|{normalized}|p1|r0",
        "normalized_label": normalized,
        "raw_label": raw_label or normalized,
        "file_name": "test.pdf",
        "company_name": "테스트회사",
        "agency": "한국신용평가㈜",
        "rating": "AA",
        "outlook": "안정적",
        "evaluation_type": "본",
        "label_text": raw_label or normalized,
        "suggestions": [{"instrument_key": "issuer", "score": 20.0, "reasons": []}],
    }


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "admin.db"


def test_insert_new_candidate(db_path: Path) -> None:
    upsert_occurrences([_occurrence("신규라벨")], db_path=db_path)
    pending = list_pending(db_path=db_path)
    assert len(pending) == 1
    assert pending[0]["normalized_label"] == "신규라벨"
    assert pending[0]["status"] == "pending"
    assert pending[0]["occurrence_count"] == 1


def test_rediscover_increments_count(db_path: Path) -> None:
    upsert_occurrences(
        [_occurrence("반복라벨", occurrence_id="id1")],
        db_path=db_path,
    )
    upsert_occurrences(
        [_occurrence("반복라벨", occurrence_id="id2", raw_label="반복 라벨")],
        db_path=db_path,
    )
    pending = list_pending(db_path=db_path)
    assert pending[0]["occurrence_count"] == 2
    assert pending[0]["raw_label"] == "반복 라벨"


def test_same_occurrence_id_no_double_count(db_path: Path) -> None:
    occ = _occurrence("동일id", occurrence_id="same-id")
    upsert_occurrences([occ], db_path=db_path)
    upsert_occurrences([occ], db_path=db_path)
    pending = list_pending(db_path=db_path)
    assert pending[0]["occurrence_count"] == 1


def test_approved_stays_approved(db_path: Path) -> None:
    upsert_occurrences([_occurrence("승인라벨")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    set_candidate_status(candidate["id"], "approved", db_path=db_path)
    upsert_occurrences(
        [_occurrence("승인라벨", occurrence_id="new-id")],
        db_path=db_path,
    )
    assert list_pending(db_path=db_path) == []
    counts = count_by_status(db_path=db_path)
    assert counts["approved"] == 1


def test_ignored_not_in_pending_list(db_path: Path) -> None:
    upsert_occurrences([_occurrence("제외라벨")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    set_candidate_status(candidate["id"], "ignored", db_path=db_path)
    assert list_pending(db_path=db_path) == []


def test_pending_to_approved(db_path: Path) -> None:
    upsert_occurrences([_occurrence("승인전환")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    updated = set_candidate_status(candidate["id"], "approved", db_path=db_path)
    assert updated is not None
    assert updated["status"] == "approved"
    assert updated["reviewed_at"] is not None


def test_pending_to_ignored(db_path: Path) -> None:
    upsert_occurrences([_occurrence("제외전환")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    updated = set_candidate_status(candidate["id"], "ignored", db_path=db_path)
    assert updated is not None
    assert updated["status"] == "ignored"


def test_ignored_to_pending_unignore(db_path: Path) -> None:
    upsert_occurrences([_occurrence("복구라벨")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    set_candidate_status(candidate["id"], "ignored", db_path=db_path)
    set_candidate_status(candidate["id"], "pending", db_path=db_path)
    pending = list_pending(db_path=db_path)
    assert len(pending) == 1
    assert pending[0]["normalized_label"] == "복구라벨"


def test_review_history_written(db_path: Path) -> None:
    init_db(db_path)
    upsert_occurrences([_occurrence("이력라벨")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    add_review_history(
        candidate_id=candidate["id"],
        action="approve",
        instrument_key="issuer",
        alias="이력라벨",
        reviewer="테스터",
        db_path=db_path,
    )
    history = list_review_history(db_path=db_path)
    assert len(history) == 1
    assert history[0]["action"] == "approve"
    assert history[0]["reviewer"] == "테스터"


def test_reconcile_pending_to_approved_is_idempotent(
    db_path: Path,
) -> None:
    upsert_occurrences([_occurrence("신규라벨")], db_path=db_path)
    lookup = {
        "신규라벨": {
            "alias": "신규 라벨",
            "instrument_key": "issuer",
        }
    }

    first = reconcile_candidate_statuses(lookup, db_path=db_path)
    second = reconcile_candidate_statuses(lookup, db_path=db_path)

    assert first["approved"] == 1
    assert second["approved"] == 0
    assert count_by_status(db_path=db_path)["approved"] == 1
    history = list_review_history(db_path=db_path)
    assert [item["action"] for item in history] == ["sync_approve"]


def test_reconcile_removed_approved_alias_to_pending(
    db_path: Path,
) -> None:
    upsert_occurrences([_occurrence("원본라벨")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    set_candidate_status(candidate["id"], "approved", db_path=db_path)
    add_review_history(
        candidate_id=candidate["id"],
        action="approve",
        instrument_key="issuer",
        alias="승인별칭",
        db_path=db_path,
    )

    stats = reconcile_candidate_statuses({}, db_path=db_path)

    assert stats["reopened"] == 1
    assert list_pending(db_path=db_path)[0]["id"] == candidate["id"]
    assert list_review_history(db_path=db_path)[0]["action"] == "sync_reopen"


def test_reconcile_uses_edited_approval_alias(db_path: Path) -> None:
    upsert_occurrences([_occurrence("원본라벨")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    set_candidate_status(candidate["id"], "approved", db_path=db_path)
    add_review_history(
        candidate_id=candidate["id"],
        action="approve",
        instrument_key="issuer",
        alias="수정별칭",
        db_path=db_path,
    )
    lookup = {
        "수정별칭": {
            "alias": "수정별칭",
            "instrument_key": "issuer",
        }
    }

    stats = reconcile_candidate_statuses(lookup, db_path=db_path)

    assert stats["reopened"] == 0
    updated = get_candidate_by_id(candidate["id"], db_path=db_path)
    assert updated is not None
    assert updated["status"] == "approved"


def test_reconcile_reassigned_alias_is_idempotent(db_path: Path) -> None:
    upsert_occurrences([_occurrence("매핑라벨")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    set_candidate_status(candidate["id"], "approved", db_path=db_path)
    add_review_history(
        candidate_id=candidate["id"],
        action="approve",
        instrument_key="issuer",
        alias="매핑라벨",
        db_path=db_path,
    )
    lookup = {
        "매핑라벨": {
            "alias": "매핑라벨",
            "instrument_key": "senior_unsecured",
        }
    }

    first = reconcile_candidate_statuses(lookup, db_path=db_path)
    second = reconcile_candidate_statuses(lookup, db_path=db_path)

    assert first["reassigned"] == 1
    assert second["reassigned"] == 0
    actions = [item["action"] for item in list_review_history(db_path=db_path)]
    assert actions == ["sync_reassign", "approve"]


def test_reconcile_does_not_change_ignored(db_path: Path) -> None:
    upsert_occurrences([_occurrence("제외동기화")], db_path=db_path)
    candidate = list_pending(db_path=db_path)[0]
    set_candidate_status(candidate["id"], "ignored", db_path=db_path)
    lookup = {
        "제외동기화": {
            "alias": "제외동기화",
            "instrument_key": "issuer",
        }
    }

    reconcile_candidate_statuses(lookup, db_path=db_path)

    assert count_by_status(db_path=db_path)["ignored"] == 1
    assert list_review_history(db_path=db_path) == []


def test_occurrence_count_and_latest_history(db_path: Path) -> None:
    from admin.services.candidate_store import (
        get_occurrence_count_by_normalized,
        latest_history_by_instrument,
        list_distinct_agencies,
    )

    upsert_occurrences(
        [_occurrence("발견횟수", occurrence_id="id1")],
        db_path=db_path,
    )
    upsert_occurrences(
        [_occurrence("발견횟수", occurrence_id="id2")],
        db_path=db_path,
    )
    assert get_occurrence_count_by_normalized("발견횟수", db_path=db_path) == 2
    assert get_occurrence_count_by_normalized("없는라벨", db_path=db_path) is None

    candidate = list_pending(db_path=db_path)[0]
    add_review_history(
        candidate_id=candidate["id"],
        action="approve",
        instrument_key="issuer",
        alias="발견횟수",
        reviewer="관리자",
        db_path=db_path,
    )
    latest = latest_history_by_instrument(db_path=db_path)
    assert "issuer" in latest
    assert "한국신용평가㈜" in list_distinct_agencies(db_path=db_path)
