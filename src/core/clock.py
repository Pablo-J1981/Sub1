"""활성 사용 시간 판정 (Qt/Win32 비의존).

활성 = 마지막 입력 후 idle_pause_s 이내. GetLastInputInfo 값(idle_s)을 받아 판정한다.
시간 배속은 펫 안의 시간에만 곱한다 (호출하는 쪽에서 처리).
"""

from __future__ import annotations


def is_active(idle_s: float, pause_s: float) -> bool:
    return idle_s < pause_s
