"""undefined 전용 추천 Key·점수 (자동 확정에 사용하지 않음).

순수 Python char n-gram cosine 유사도.
추천 파라미터는 `common.matching_policy.RECOMMENDATION`이 단일 원천이다.
"""

from __future__ import annotations

import math
from collections import Counter

from common.matching_policy import RECOMMENDATION, normalize_label
from common.models import Suggestion
from common.settings import InstrumentsConfig


def _char_ngrams(text: str, n: int) -> Counter[str]:
    if len(text) < n:
        return Counter([text] if text else [])
    return Counter(text[i : i + n] for i in range(len(text) - n + 1))


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    dot = sum(a[token] * b[token] for token in shared)
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def recommend_instruments(
    normalized_label: str,
    config: InstrumentsConfig,
    *,
    top_k: int | None = None,
) -> list[Suggestion]:
    """undefined 라벨에 대해 instrument_key 추천 목록을 생성한다."""
    n = RECOMMENDATION.ngram_size
    k = RECOMMENDATION.top_k if top_k is None else top_k
    min_score = RECOMMENDATION.min_score

    query = _char_ngrams(normalized_label, n)

    key_vectors: dict[str, Counter[str]] = {
        key: Counter() for key in config.instruments
    }
    for entry in config.label_dictionary:
        if not entry.active:
            continue
        key_vectors[entry.instrument_key].update(
            _char_ngrams(normalize_label(entry.raw_label), n)
        )

    scored: list[tuple[str, float]] = []
    for instrument_key, vector in key_vectors.items():
        if not vector:
            continue
        score = _cosine(query, vector) * 100.0
        if score > 0:
            scored.append((instrument_key, score))

    scored.sort(key=lambda item: item[1], reverse=True)

    suggestions: list[Suggestion] = []
    for instrument_key, score in scored[:k]:
        if score < min_score:
            continue
        display = config.instruments[instrument_key].display_name
        suggestions.append(
            Suggestion(
                instrument_key=instrument_key,
                score=round(score, 2),
                reasons=[
                    f"기존 {instrument_key}({display}) 라벨과 "
                    f"char n-gram cosine 유사도 {score:.1f}"
                ],
            )
        )
    return suggestions
