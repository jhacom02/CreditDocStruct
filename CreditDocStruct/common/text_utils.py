"""라벨 정규화 호환 계층.

실제 정책은 `common.matching_policy`에 있다.
기존 import 경로(`common.text_utils`)를 유지하기 위해 재-export한다.
"""

from __future__ import annotations

from common.matching_policy import normalize_label, normalize_text

__all__ = ["normalize_label", "normalize_text"]
