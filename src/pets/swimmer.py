"""헤엄치는 타입(SwimmerPet, 상어): 중력 없이 모니터 작업 영역 안을 천천히 헤엄친다 (Qt/Win32 비의존).

- 가장자리에서는 속도가 서서히 줄었다가 안쪽으로 돌아선다 (급격히 튕기지 않는다).
- 먹이가 보이면 (가라앉는 중이라도) 그쪽으로 헤엄쳐 가서 먹는다.
- 빠르게 다가오는 커서에는 잠깐 놀라 달아난다.
- 죽으면 바닥까지 가라앉고, 그 자리에서 무덤이 된다.
"""

from __future__ import annotations

import math
import random
from enum import Enum, auto

from core.config import PhysicsConfig, SwimmerConfig
from core.feeding import Reach
from core.geometry import Rect
from core.world import WorldSnapshot
from pets.base import PetBody


class SwimState(Enum):
    SWIM = auto()
    STARTLED = auto()
    EAT = auto()
    HELD = auto()
    SINK = auto()     # 죽어서 가라앉는 중
    SETTLED = auto()  # 바닥에 가라앉음 (무덤이 된다)


_ACTION = {
    SwimState.SWIM: "swim",
    SwimState.STARTLED: "startled",
    SwimState.EAT: "eat",
    SwimState.HELD: "held",
    SwimState.SINK: "die",
    SwimState.SETTLED: "die",
}
_FOOD_SPEED_MUL = 1.8     # 먹이 쪽으로 갈 때 속도 배수
_EAT_REACH_ORIG_PX = 4.0  # 원본 px. 이 거리 안이면 먹이에 닿았다고 본다
_EDGE_EPS = 0.5


class SwimmerPet(PetBody):
    movement = "swimmer"

    def __init__(
        self,
        *,
        width: float,
        ground_offset: float,
        unit: float,
        physics: PhysicsConfig,
        behavior: SwimmerConfig,
        rng: random.Random,
        below: float = 0.0,
    ) -> None:
        super().__init__(width=width, ground_offset=ground_offset, unit=unit, below=below)
        self._beh = behavior
        self._rng = rng
        self._max_step = physics.max_step_s
        self._speed = behavior.swim_speed * unit
        self._sink = behavior.sink_speed * unit
        # 방향을 바꿀 때 turn_s 가 걸리도록 가속도를 정한다 (속도 0에서 반대 방향 최고 속도까지)
        self._accel = 2.0 * self._speed / behavior.turn_s if behavior.turn_s > 0 else 1e9
        self._startle_speed = behavior.startle_speed * unit
        self._startle_radius = behavior.startle_radius * unit
        self._startle_min_speed = behavior.startle_cursor_speed * unit
        self._eat_reach = _EAT_REACH_ORIG_PX * unit

        self.vx = 0.0
        self.vy = 0.0
        self.state = SwimState.SWIM
        self.timer = 0.0
        self._work: Rect | None = None
        self._goal_vx = self._speed * rng.choice((-1, 1))
        self._goal_vy = 0.0
        self._retarget_left = 0.0
        self._food: tuple[float, float] | None = None
        self._at_food = False
        self._meal_done = False
        self._flee = (0.0, 0.0)
        self._pick_goal()

    def place(self, cx: float, feet_y: float) -> None:
        self.cx = float(cx)
        self.feet_y = float(feet_y)
        self.vx = 0.0
        self.vy = 0.0
        self.state = SwimState.SWIM
        self._clear_food()
        self._pick_goal()

    # ------------------------------------------------------------------ 외부 인터페이스

    def action(self) -> str:
        return _ACTION[self.state]

    def is_grounded(self) -> bool:
        return False

    def settled(self) -> bool:
        return self.state is SwimState.SETTLED

    def hold(self, cx: float, feet_y: float) -> None:
        self.state = SwimState.HELD
        self.vx = 0.0
        self.vy = 0.0
        self._clear_food()
        work = self._work
        if work is not None:
            half = self.half_width
            lo, hi = work.left + half, work.right - half
            if lo <= hi:
                cx = min(max(cx, lo), hi)
            feet_y = min(max(feet_y, work.top + self.ground_offset), work.bottom)
        self.cx = float(cx)
        self.feet_y = float(feet_y)

    def release(self, vx: float, vy: float) -> None:
        if self.state is not SwimState.HELD:
            return
        self.state = SwimState.SWIM
        self.vx = float(vx)
        self.vy = float(vy)
        self._pick_goal()

    def on_petted(self, seconds: float) -> None:
        """헤엄치는 펫은 쓰다듬어도 멈추지 않는다 (기뻐하는 그림은 창에서 보인다)."""

    def pin(self, cx: float, feet_y: float) -> None:
        super().pin(cx, feet_y)
        self.state = SwimState.SETTLED

    def set_frozen(self, frozen: bool) -> None:
        if frozen:
            if self.state not in (SwimState.SINK, SwimState.SETTLED):
                self.state = SwimState.SINK
            self._clear_food()
            self.vx = 0.0
            self.vy = 0.0
        elif self.state in (SwimState.SINK, SwimState.SETTLED):
            self.state = SwimState.SWIM

    def observe_cursor(self, x: float, y: float, speed: float) -> None:
        if self.state not in (SwimState.SWIM, SwimState.EAT):
            return
        if speed < self._startle_min_speed:
            return
        dx = self.cx - x
        dy = self._center_y() - y
        dist = math.hypot(dx, dy)
        if dist > self._startle_radius:
            return
        if dist < 1e-6:
            dx, dy, dist = 1.0, 0.0, 1.0
        self._flee = (dx / dist * self._startle_speed, dy / dist * self._startle_speed)
        self._clear_food()
        self.state = SwimState.STARTLED
        self.timer = self._beh.startle_duration_s

    # ------------------------------------------------------------------ 먹이 관련

    def reach_food(self, x: float, y: float) -> Reach:
        if self._work is None or self.state in (
            SwimState.HELD, SwimState.SINK, SwimState.SETTLED
        ):
            return Reach.OUT
        return Reach.REACH

    def approach_food(self, x: float, y: float) -> None:
        self._food = (float(x), float(y))

    def arrived(self) -> bool:
        return self._at_food and self.state is SwimState.SWIM

    def begin_eat(self, duration: float) -> bool:
        if not self.arrived():
            return False
        self.state = SwimState.EAT
        self.timer = float(duration)
        self.vx = 0.0
        self.vy = 0.0
        return True

    def is_eating(self) -> bool:
        return self.state is SwimState.EAT

    def take_meal(self) -> bool:
        if not self._meal_done:
            return False
        self._meal_done = False
        return True

    def cancel_walk(self) -> None:
        self._clear_food()

    # ------------------------------------------------------------------ 물리 한 단계

    def update(self, dt: float, world: WorldSnapshot) -> None:
        dt = min(max(dt, 0.0), self._max_step)
        mon = world.monitor_for(self.cx)
        if mon is None:
            return
        self._work = mon.rect  # 헤엄은 모니터 전체 (작업 표시줄 위아래까지)
        st = self.state

        if st is SwimState.HELD:
            return
        if st in (SwimState.SINK, SwimState.SETTLED):
            self._sink_step(dt)
            return

        if st is SwimState.STARTLED:
            self.timer -= dt
            if self.timer <= 0:
                self.state = SwimState.SWIM
                self._pick_goal()
                self._steer(dt, self._flee, mul=3.0)
        elif st is SwimState.EAT:
            self.timer -= dt
            self._steer(dt, (0.0, 0.0), mul=3.0)
            if self.timer <= 0:
                self._clear_food()
                self._meal_done = True
                self.state = SwimState.SWIM
        else:
            if self._food is not None:
                self._steer(dt, self._food_velocity(), mul=3.0)
            else:
                self._retarget_left -= dt
                if self._retarget_left <= 0:
                    self._pick_goal()
                self._turn_at_edges()
                self._steer(dt, (self._goal_vx, self._goal_vy))

        self._integrate(dt)

    # ------------------------------------------------------------------ 내부

    def _center_y(self) -> float:
        """몸통 중심 y (창 윗변 + 그림 높이의 절반)."""
        return self.feet_y + (self.below - self.ground_offset) / 2

    def _food_velocity(self) -> tuple[float, float]:
        assert self._food is not None
        fx, fy = self._food
        dx = fx - self.cx
        dy = fy - self._center_y()
        dist = math.hypot(dx, dy)
        if dist <= self._eat_reach:
            self._at_food = True
            return (0.0, 0.0)
        self._at_food = False
        speed = self._speed * _FOOD_SPEED_MUL
        return (dx / dist * speed, dy / dist * speed)

    def _clear_food(self) -> None:
        self._food = None
        self._at_food = False

    def _pick_goal(self) -> None:
        lo, hi = self._beh.retarget_s
        self._retarget_left = self._rng.uniform(lo, hi)
        sign = self._rng.choice((-1, 1))
        self._goal_vx = sign * self._speed * self._rng.uniform(0.6, 1.0)
        self._goal_vy = self._speed * self._rng.uniform(-0.3, 0.3)

    def _turn_at_edges(self) -> None:
        """가장자리에 닿으면 안쪽을 향하는 목표로 바꾼다. 실제 방향 전환은 _steer가 천천히 한다."""
        work = self._work
        if work is None:
            return
        half = self.half_width
        lo, hi = work.left + half, work.right - half
        top = work.top + self.ground_offset
        bottom = float(work.bottom) - self.below
        # 제동 거리(속도가 0이 되는 데 필요한 거리) 안에 들어오면 미리 방향을 돌린다
        margin = self._speed * self._beh.turn_s / 2 + _EDGE_EPS
        if lo <= hi:
            if self.cx <= lo + margin and self._goal_vx < 0:
                self._goal_vx = self._speed
            elif self.cx >= hi - margin and self._goal_vx > 0:
                self._goal_vx = -self._speed
        vmargin = self._speed * self._beh.turn_s * 0.15 + _EDGE_EPS
        if self.feet_y <= top + vmargin and self._goal_vy < 0:
            self._goal_vy = self._speed * 0.3
        elif self.feet_y >= bottom - vmargin and self._goal_vy > 0:
            self._goal_vy = -self._speed * 0.3

    def _steer(self, dt: float, desired: tuple[float, float], mul: float = 1.0) -> None:
        step = self._accel * mul * dt
        dvx, dvy = desired
        self.vx += min(max(dvx - self.vx, -step), step)
        self.vy += min(max(dvy - self.vy, -step), step)

    def _integrate(self, dt: float) -> None:
        """속도대로 움직이고, 작업 영역 밖으로 나가면 멈춘다."""
        self.cx += self.vx * dt
        self.feet_y += self.vy * dt
        work = self._work
        if work is None:
            return
        half = self.half_width
        lo, hi = work.left + half, work.right - half
        top = work.top + self.ground_offset
        bottom = work.bottom - self.below
        if lo <= hi:
            if self.cx < lo:
                self.cx, self.vx = lo, max(self.vx, 0.0)
            elif self.cx > hi:
                self.cx, self.vx = hi, min(self.vx, 0.0)
        if top <= bottom:
            if self.feet_y < top:
                self.feet_y, self.vy = top, max(self.vy, 0.0)
            elif self.feet_y > bottom:
                self.feet_y, self.vy = bottom, min(self.vy, 0.0)

    def _sink_step(self, dt: float) -> None:
        work = self._work
        self.vx = 0.0
        self.vy = 0.0
        if work is None or self.state is not SwimState.SINK:
            return
        floor = float(work.bottom) - self.below
        self.feet_y = min(self.feet_y + self._sink * dt, floor)
        if self.feet_y >= floor - 1e-6:
            self.state = SwimState.SETTLED
