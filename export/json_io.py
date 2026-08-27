"""개발자용 JSON 저장 (임시 파일 생성).

Plan: CreditDocStruct_restructure_43c68190 섹션 G-1 참고.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_results_json_tmp(
    results: list[dict[str, Any]],
    final_path: str | Path,
) -> Path:
    """`final_path.tmp`에 JSON 배열을 쓰고 tmp 경로를 반환한다."""
    final_path = Path(final_path)
    tmp_path = final_path.with_name(final_path.name + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)

    return tmp_path
