"""데스크톱 펫 진입점.

개발 실행:  python src/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# `python src/main.py` 로 실행해도 core, ui, platform_win 패키지를 찾도록 설정
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())
