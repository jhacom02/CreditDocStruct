"""UI 헬퍼·결과 서비스 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from admin.services.result_service import (
    ResultServiceError,
    build_excel_bytes,
    filter_results,
    list_result_files,
    load_results_json,
    summarize_results,
)
from admin.ui.copy import (
    action_label,
    clamp_index,
    default_instrument_key,
    filter_candidates,
    history_sentence,
    next_index_after_remove,
    recommendation_strength,
    sort_suggestions,
    top_suggestions,
)
from common.settings import get_instruments_config


def test_sort_suggestions_descending() -> None:
    items = [
        {"instrument_key": "a", "score": 10},
        {"instrument_key": "b", "score": 25},
        {"instrument_key": "c", "score": 15},
    ]
    sorted_items = sort_suggestions(items)
    assert [item["instrument_key"] for item in sorted_items] == ["b", "c", "a"]


def test_top_suggestions_limit() -> None:
    items = [
        {"instrument_key": f"k{i}", "score": float(i)}
        for i in range(5)
    ]
    top = top_suggestions(items, limit=3)
    assert len(top) == 3
    assert top[0]["instrument_key"] == "k4"


def test_default_instrument_key_from_top() -> None:
    items = [{"instrument_key": "issuer", "score": 30}]
    assert default_instrument_key(items) == "issuer"


def test_default_instrument_key_empty() -> None:
    assert default_instrument_key([]) is None


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (60, "비교적 유사함"),
        (59.9, "확인 필요"),
        (30, "확인 필요"),
        (29.9, "추천 신뢰 낮음"),
        (None, "추천 정보 없음"),
    ],
)
def test_recommendation_strength(score: float | None, expected: str) -> None:
    assert recommendation_strength(score) == expected


def test_history_sentence_approve() -> None:
    sentence = history_sentence(
        {
            "action": "approve",
            "alias": "IFSR",
            "instrument_key": "insurance_payment",
            "reviewer": "관리자",
        }
    )
    assert "IFSR" in sentence
    assert "등록" in sentence


def test_history_sentence_sync_approve() -> None:
    assert action_label("sync_approve") == "기존 등록 라벨 동기화"
    sentence = history_sentence(
        {
            "action": "sync_approve",
            "alias": "IFSR",
            "instrument_key": "insurance_payment",
        }
    )
    assert "동기화" in sentence


def test_filter_candidates_by_agency_and_company() -> None:
    items = [
        {
            "agency": "NICE신용평가㈜",
            "company_name": "경남은행",
            "last_seen_at": "2026-07-21T10:00:00+09:00",
        },
        {
            "agency": "한국신용평가㈜",
            "company_name": "우리은행",
            "last_seen_at": "2026-07-21T10:00:00+09:00",
        },
    ]
    filtered = filter_candidates(
        items,
        agency="NICE신용평가㈜",
        company_query="경남",
        period="전체",
    )
    assert len(filtered) == 1
    assert filtered[0]["company_name"] == "경남은행"


def test_next_index_and_clamp() -> None:
    assert next_index_after_remove(0, 0) == 0
    assert next_index_after_remove(2, 2) == 1
    assert next_index_after_remove(1, 3) == 1
    assert clamp_index(5, 3) == 2
    assert clamp_index(-1, 3) == 0


def _sample_results() -> list[dict]:
    return [
        {
            "result_no": 1,
            "file_name": "a.pdf",
            "file_hash": "h1",
            "company_name": "경남은행",
            "agency": "한국기업평가㈜",
            "status": "success",
            "fail_reason": None,
            "products": [
                {
                    "instrument_key": "coco_t1",
                    "raw_label": "COCO(신종)",
                    "rating": "A+",
                    "outlook": "안정적",
                    "evaluation_type": "본",
                    "status": "success",
                    "fail_reason": None,
                }
            ],
            "records": [],
            "validation_warnings": [],
        },
        {
            "result_no": 2,
            "file_name": "b.pdf",
            "file_hash": "h2",
            "company_name": "테스트사",
            "agency": "NICE신용평가㈜",
            "status": "fail",
            "fail_reason": {
                "code": "undefined_label",
                "message": "미등록 라벨",
            },
            "products": [],
            "records": [],
            "validation_warnings": [],
        },
    ]


def test_list_and_load_result_files(tmp_path: Path) -> None:
    older = tmp_path / "result_old.json"
    newer = tmp_path / "result_new.json"
    older.write_text("[]", encoding="utf-8")
    newer.write_text(json.dumps(_sample_results(), ensure_ascii=False), encoding="utf-8")
    listed = list_result_files(tmp_path)
    assert [item.name for item in listed][0] in {"result_new.json", "result_old.json"}
    assert len(listed) == 2
    loaded = load_results_json(newer)
    assert len(loaded) == 2


def test_load_results_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ResultServiceError):
        load_results_json(path)


def test_filter_and_summarize_results() -> None:
    results = _sample_results()
    filtered = filter_results(
        results,
        status="fail",
        fail_code="undefined_label",
        query="테스트",
    )
    assert len(filtered) == 1
    summary = summarize_results(results)
    assert summary == {"total": 2, "success": 1, "partial": 0, "fail": 1}


def test_build_excel_bytes_columns() -> None:
    config = get_instruments_config()
    payload = build_excel_bytes(_sample_results(), config)
    assert payload[:2] == b"PK"
    assert len(payload) > 100
