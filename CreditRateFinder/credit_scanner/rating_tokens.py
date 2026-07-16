from __future__ import annotations

from typing import Iterable

from credit_scanner.constants import OUTLOOK_TOKEN_RE, RATING_TOKEN_RE
from credit_scanner.text_utils import normalize_outlook, normalize_text


def parse_rating_value(value: str | None) -> dict[str, str | None] | None:
    if not value:
        return None

    normalized = normalize_text(value)
    normalized = normalized.strip(" ,;:[]{}")

    match = RATING_TOKEN_RE.fullmatch(normalized)

    if not match:
        return None

    rating = match.group("rating").upper()
    sf = match.group("sf")
    outlook = normalize_outlook(match.group("outlook"))

    if sf:
        rating = f"{rating}(sf)"

    rating_display = f"{rating}/{outlook}" if outlook else rating

    return {
        "rating": rating,
        "outlook": outlook,
        "rating_display": rating_display,
    }


def find_rating_tokens(
    values: Iterable[str],
) -> list[tuple[int, dict[str, str | None]]]:
    tokens = [normalize_text(value) for value in values]
    results: list[tuple[int, dict[str, str | None]]] = []

    index = 0

    while index < len(tokens):
        value = tokens[index]
        parsed = parse_rating_value(value)

        if parsed:
            if parsed["outlook"] is None and index + 1 < len(tokens):
                outlook_match = OUTLOOK_TOKEN_RE.fullmatch(tokens[index + 1])

                if outlook_match:
                    outlook = normalize_outlook(
                        outlook_match.group("outlook")
                    )
                    parsed = {
                        "rating": parsed["rating"],
                        "outlook": outlook,
                        "rating_display": f"{parsed['rating']}/{outlook}",
                    }
                    index += 1

            results.append((index, parsed))

        index += 1

    return results


def tokenize_values(values: Iterable[str]) -> list[str]:
    tokens: list[str] = []

    for value in values:
        normalized = normalize_text(value)

        if not normalized:
            continue

        tokens.extend(
            token
            for token in normalized.replace("\n", " ").split(" ")
            if token
        )

    return tokens
