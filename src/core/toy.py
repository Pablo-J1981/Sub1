"""공 장난감 (Qt/Win32 비의존).

- 공은 한 번에 하나만 있다. 놓으면 발판 위에 자리 잡고, play_s(실제 시간) 뒤 사라진다.
- 펫은 공을 쫓아가고, 닿으면 밀어 굴린다. 밀린 공은 friction 으로 천천히 멈춘다.
- 펫은 같은 높이 발판에 있을 때만 공을 가지고 논다 (먹이 찾기와 같은 규칙).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.config import ToyConfig
from core.feeding import Reach

if TYPE_CHECKING:
    from pets.base import PetBody


@dataclass
class Ball:
    x: float
    y: float          # 놓인 발판 높이
    left: float       # 굴러갈 수 있는 범위 (발판 양 끝)
    right: float
    half_w: float     # 공 반지름 (물리 px)
    v: float = 0.0    # 현재 굴러가는 속도 (물리 px/s)
    remaining_s: float = 0.0


class BallToy:
    def __init__(self, cfg: ToyConfig, unit: float) -> None:
        self._cfg = cfg
        self._unit = float(unit)
        self.ball: Ball | None = None

    def drop(self, x: float, y: float, left: float, right: float, half_w: float) -> Ball:
        self.ball = Ball(float(x), float(y), float(left), float(right), float(half_w),
                         remaining_s=self._cfg.play_s)
        self._clamp()
        return self.ball

    def remove(self) -> None:
        self.ball = None

    def step(self, dt: float) -> None:
        b = self.ball
        if b is None:
            return
        dt = max(0.0, dt)
        b.remaining_s -= dt
        if b.remaining_s <= 0:
            self.ball = None
            return
        friction = self._cfg.friction * self._unit * dt
        if abs(b.v) <= friction:
            b.v = 0.0
        else:
            b.v -= friction if b.v > 0 else -friction
        b.x += b.v * dt
        self._clamp()

    def tick_pet(self, body: PetBody) -> None:
        """펫 한 마리가 공을 쫓고 민다."""
        b = self.ball
        if b is None or body.reach_food(b.x, b.y) is not Reach.REACH:
            return
        gap = b.x - body.cx
        if abs(gap) <= body.half_width + b.half_w:
            direction = 1 if gap >= 0 else -1
            b.v = direction * self._cfg.push_speed * self._unit
            body.facing = direction
        body.approach_food(b.x, b.y)

    def _clamp(self) -> None:
        b = self.ball
        if b is None:
            return
        lo, hi = b.left + b.half_w, b.right - b.half_w
        if lo > hi:
            return
        if b.x < lo or b.x > hi:
            b.x = min(max(b.x, lo), hi)
            b.v = 0.0
