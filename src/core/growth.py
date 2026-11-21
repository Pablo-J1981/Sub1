"""성장 단계 계산 (Qt/Win32 비의존).

단계 n → n+1 은 활성 시간과 누적 먹은 횟수를 '둘 다' 채워야 한다 (AND).
한 번 오른 단계는 내려가지 않는다.
"""

from __future__ import annotations

MAX_STAGE = 5


def stage_for(
    active_s: float,
    meals: int,
    *,
    hours: tuple[float, ...],
    meal_counts: tuple[int, ...],
    current: int = 1,
) -> int:
    stage = min(max(1, current), MAX_STAGE)
    while stage < MAX_STAGE:
        i = stage - 1
        if active_s >= hours[i] * 3600.0 and meals >= meal_counts[i]:
            stage += 1
        else:
            break
    return stage


def pixel_scale_for(stage: int, scales: tuple[int, ...]) -> int:
    return scales[min(max(stage, 1), len(scales)) - 1]
