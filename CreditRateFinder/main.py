"""CreditRateFinder 진입점 (유일한 오케스트레이션).

TODO: 인자 파싱 → PDF 순회 → 추출(extract) → 회사명/신평사(agency) →
분류(classify) → status/fail_reason 판정 → JSON+Excel 동시 저장(export) →
admin/undefined.json 누적까지 이 파일에서 조립한다.

Plan: creditratefinder_restructure_43c68190 참고.
공개 API: `from main import extract_credit_report` (구현 예정)
CLI: `python main.py <dir|pdf> [--target KEY]`
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> None:
    raise NotImplementedError(
        "main 오케스트레이션은 아직 구현되지 않았습니다. "
        "Plan 작업 순서(B~G)를 따라 채워주세요."
    )


if __name__ == "__main__":
    main()
