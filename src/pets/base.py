"""모든 동물의 공통 베이스 (Qt 비의존).

좌표는 물리 픽셀 기준이다.
- cx: 몸통 중심 x
- feet_y: 발이 닿는 y (발판 윗변과 같은 값)
- ground_offset: 창 윗변에서 발까지 거리 (그림에서 발 위치로 계산)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.world import WorldSnapshot


class PetBody(ABC):
    movement: str = ""

    def __init__(self, *, width: float, ground_offset: float, unit: float) -> None:
        if unit <= 0:
            raise ValueError("unit 은 0보다 커야 합니다.")
        self.width = float(width)
        self.ground_offset = float(ground_offset)
        self.unit = float(unit)  # 물리 픽셀 / 원본 픽셀
        self.cx = 0.0
        self.feet_y = 0.0
        self.facing = 1  # +1 오른쪽, -1 왼쪽 (왼쪽은 그림을 좌우 반전)

    @property
    def half_width(self) -> float:
        return self.width / 2

    @property
    def window_left(self) -> float:
        return self.cx - self.half_width

    @property
    def window_top(self) -> float:
        return self.feet_y - self.ground_offset

    @abstractmethod
    def update(self, dt: float, world: WorldSnapshot) -> None:
        """dt초 동안 세계 상태에 맞춰 한 단계 움직인다."""

    @abstractmethod
    def action(self) -> str:
        """지금 보여 줄 동작 이름 (pet.json의 actions 키)."""
