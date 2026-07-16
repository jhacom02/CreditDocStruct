"""config/instruments.yaml의 `normalization` 규칙 적용 유틸리티.

규칙: NFKC, trim, 줄바꿈 제거, 괄호/대시 정규화, 영문 대문자,
lookup(label_dictionary exact match)용 공백 완전 제거.

Plan: creditratefinder_restructure_43c68190 섹션 C 참고.
"""

from __future__ import annotations

import re
import unicodedata

_BRACKET_MAP = {
    "（": "(",
    "）": ")",
    "［": "(",
    "］": ")",
    "【": "(",
    "】": ")",
}

_DASH_MAP = {
    "－": "-",
    "−": "-",
    "–": "-",
    "—": "-",
}


def normalize_text(value: str | None) -> str:
    """사람이 읽을 수 있는 정규화 형태(공백은 단일 스페이스로 유지)."""
    if not value:
        return ""

    text = unicodedata.normalize("NFKC", str(value))

    for source, target in _BRACKET_MAP.items():
        text = text.replace(source, target)
    for source, target in _DASH_MAP.items():
        text = text.replace(source, target)

    text = text.replace("／", "/").replace("：", ":")

    # 줄바꿈 제거(공백으로 치환 후 중복 공백 정리)
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    # 영문 대문자화(한글 등 비ASCII 문자는 그대로 유지)
    text = "".join(
        char.upper() if char.isascii() and char.isalpha() else char
        for char in text
    )

    return text


def normalize_label(value: str | None) -> str:
    """`label_dictionary` exact match용 lookup 키(공백 완전 제거)."""
    return re.sub(r"\s+", "", normalize_text(value))
