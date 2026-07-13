"""하위 호환: 오케스트레이션은 프로젝트 루트 main.py 에 있습니다."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from main import main  # noqa: E402

__all__ = ["main"]
