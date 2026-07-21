"""matching_policy 단위 테스트."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from classify.recommend import recommend_instruments
from common.matching_policy import (
    MatchingPolicyError,
    RECOMMENDATION,
    build_normalized_lookup,
    find_alias_conflict,
    normalize_label,
    normalize_text,
)
from common.settings import (
    InstrumentDefinition,
    InstrumentsConfig,
    InstrumentsConfigError,
    LabelDictionaryEntry,
    load_instruments_config,
)


def test_recommendation_defaults() -> None:
    assert RECOMMENDATION.ngram_size == 2
    assert RECOMMENDATION.top_k == 3
    assert RECOMMENDATION.min_score == 15.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  ab  c  ", "AB C"),
        ("（신종）", "(신종)"),
        ("Ａ－１", "A-1"),
        ("issuer\nrating", "ISSUER RATING"),
        ("／：", "/:"),
    ],
)
def test_normalize_text_variants(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("무보증 사채", "무보증사채"),
        ("Issuer Rating", "ISSUERRATING"),
        ("  CP  ", "CP"),
    ],
)
def test_normalize_label_strips_whitespace(raw: str, expected: str) -> None:
    assert normalize_label(raw) == expected


def test_build_normalized_lookup_rejects_unknown_key() -> None:
    entries = [
        SimpleNamespace(
            raw_label="발행자",
            instrument_key="missing",
            active=True,
        )
    ]
    with pytest.raises(MatchingPolicyError, match="등록되지 않은"):
        build_normalized_lookup({"issuer": object()}, entries)


def test_build_normalized_lookup_rejects_conflict() -> None:
    entries = [
        SimpleNamespace(raw_label="무보증사채", instrument_key="a", active=True),
        SimpleNamespace(
            raw_label="무보증 사채",
            instrument_key="b",
            active=True,
        ),
    ]
    with pytest.raises(MatchingPolicyError, match="동일 정규화"):
        build_normalized_lookup({"a": object(), "b": object()}, entries)


def test_load_instruments_config_extra_keys_ignored(tmp_path) -> None:
    path = tmp_path / "instruments.yaml"
    path.write_text(
        """
instruments:
  issuer:
    display_name: "발행자신용등급"
label_dictionary:
  "발행자":
    instrument_key: issuer
    active: true
normalization:
  unicode_form: NFKC
recommendation:
  min_score: 99
validation:
  exact_match_only: false
""",
        encoding="utf-8",
    )
    config = load_instruments_config(path)
    assert config.normalized_lookup[normalize_label("발행자")] == "issuer"


def test_load_instruments_config_unknown_key(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
instruments:
  issuer:
    display_name: "발행자신용등급"
label_dictionary:
  "발행자":
    instrument_key: missing
    active: true
""",
        encoding="utf-8",
    )
    with pytest.raises(InstrumentsConfigError):
        load_instruments_config(path)


def test_find_alias_conflict_normalized() -> None:
    entries = [
        LabelDictionaryEntry("무보증사채", "senior_unsecured", True, ""),
    ]
    message = find_alias_conflict(
        "무보증 사채",
        "issuer",
        entries,
        known_instrument_keys=["issuer", "senior_unsecured"],
    )
    assert message is not None
    assert "정규화 충돌" in message


def test_recommend_uses_policy_min_score() -> None:
    config = InstrumentsConfig(
        instruments={
            "issuer": InstrumentDefinition("issuer", "발행자신용등급"),
            "senior_unsecured": InstrumentDefinition(
                "senior_unsecured", "무보증사채"
            ),
        },
        label_dictionary=(
            LabelDictionaryEntry("발행자신용등급", "issuer", True, ""),
            LabelDictionaryEntry("무보증사채", "senior_unsecured", True, ""),
        ),
        normalized_lookup={
            normalize_label("발행자신용등급"): "issuer",
            normalize_label("무보증사채"): "senior_unsecured",
        },
    )
    suggestions = recommend_instruments(
        normalize_label("완전무관한XYZ라벨"),
        config,
    )
    assert all(item.score >= RECOMMENDATION.min_score for item in suggestions)
    assert len(suggestions) <= RECOMMENDATION.top_k
