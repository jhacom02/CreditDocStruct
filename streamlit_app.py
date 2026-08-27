from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "CreditDocStruct"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from admin.admin_main import main

main()
