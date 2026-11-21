"""애니메이션 프레임 계산 (Qt 비의존)."""

from __future__ import annotations


def frame_index(elapsed: float, frames: int, fps: float) -> int:
    """동작을 시작한 뒤 elapsed초가 지났을 때 보여 줄 프레임 번호(0부터).

    frames가 1이면 항상 0. 프레임은 fps 속도로 반복된다.
    """
    if frames <= 1 or fps <= 0 or elapsed <= 0:
        return 0
    return int(elapsed * fps) % frames


def frame_index_once(elapsed: float, frames: int, fps: float) -> int:
    """한 번만 재생하고 마지막 프레임에서 멈추는 인덱스."""
    if frames <= 1:
        return 0
    return min(int(max(elapsed, 0.0) * fps), frames - 1)
