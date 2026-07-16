from __future__ import annotations

import re
import unicodedata

from credit_scanner.constants import EVALUATION_TYPES, OUTLOOK_MAP


def normalize_text(text: str | None) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", str(text))

    text = (
        text.replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("／", "/")
        .replace("：", ":")
        .replace("（", "(")
        .replace("）", ")")
    )

    text = re.sub(
        r"\b(AAA|AA|A|BBB|BB|B|CCC|CC|C)\s*([+-])",
        r"\1\2",
        text,
    )

    text = re.sub(
        r"\bA\s*([123])\s*([+-]?)",
        r"A\1\2",
        text,
    )

    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)

    return text.strip()


def compact_text(text: str | None) -> str:
    return re.sub(r"\s+", "", normalize_text(text)).lower()


def normalize_evaluation_type(value: str | None) -> str | None:
    if not value:
        return None

    compact = re.sub(r"\s+", "", normalize_text(value))

    for evaluation_type in EVALUATION_TYPES:
        if compact == re.sub(r"\s+", "", evaluation_type):
            return evaluation_type

    return None


def normalize_outlook(value: str | None) -> str | None:
    if not value:
        return None

    normalized = normalize_text(value)
    return OUTLOOK_MAP.get(normalized.lower(), normalized)
