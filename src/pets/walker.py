"""걷는 타입(WalkerPet): 중력, 발판 착지, 걷기, 가장자리 공포, 창 따라가기.

상태 머신
- 지상: IDLE / WALK / SIT / SLEEP (무작위 전환), SCARED (가장자리), LAND (착지 직후)
- 공중: FALL (낙하), JUMP_OFF (가장자리에서 뛰어내림)
- 특수: STARTLED (발판 창이 닫힘/최소화/최대화) -> 놀란 뒤 FALL
- 마우스: HELD (드래그로 들고 있는 중). 놓으면 던진 속도로 FALL

발판 규칙
- 발이 닿은 발판이 사라지면, 창 자체가 사라졌거나 발판 자격을 잃었으면 STARTLED,
  단지 다른 창에 가려졌으면 바로 FALL.
- 발판 창이 움직이면 같은 양만큼 함께 움직인다.
- 모니터 벽(발판이 모니터 끝과 맞닿은 쪽)에서는 뛰어내리지 않고 방향만 바꾼다.
"""

from __future__ import annotations

import random
from enum import Enum, auto

from core.config import PhysicsConfig, WalkerConfig
from core.geometry import Rect, Surface
from core.world import WorldSnapshot
from pets.base import PetBody

class WalkerState(Enum):
    IDLE = auto()
    WALK = auto()
    SIT = auto()
    SLEEP = auto()
    SCARED = auto()
    LAND = auto()
    STARTLED = auto()
    FALL = auto()
    JUMP_OFF = auto()
    HELD = auto()


BEHAVIOR_STATES = {
    "idle": WalkerState.IDLE,
    "walk": WalkerState.WALK,
    "sit": WalkerState.SIT,
    "sleep": WalkerState.SLEEP,
}
GROUNDED_STATES = frozenset({
    WalkerState.IDLE, WalkerState.WALK, WalkerState.SIT, WalkerState.SLEEP,
    WalkerState.SCARED, WalkerState.LAND,
})
AIRBORNE_STATES = frozenset({WalkerState.FALL, WalkerState.JUMP_OFF})
_ACTION_BY_STATE = {
    WalkerState.IDLE: "idle",
    WalkerState.WALK: "walk",
    WalkerState.SIT: "sit",
    WalkerState.SLEEP: "sleep",
    WalkerState.SCARED: "scared",
    WalkerState.LAND: "land",
    WalkerState.STARTLED: "scared",
    WalkerState.FALL: "fall",
    WalkerState.JUMP_OFF: "jump",
    WalkerState.HELD: "held",
}


class WalkerPet(PetBody):
    movement = "walker"

    def __init__(
        self,
        *,
        width: float,
        ground_offset: float,
        unit: float,
        physics: PhysicsConfig,
        behavior: WalkerConfig,
        rng: random.Random,
    ) -> None:
        super().__init__(width=width, ground_offset=ground_offset, unit=unit)
        self._beh = behavior
        self._rng = rng
        self._gravity = physics.gravity * unit
        self._max_fall = physics.max_fall_speed * unit
        self._tolerance = physics.support_tolerance * unit
        self._landing_s = physics.landing_duration_s
        self._max_step = physics.max_step_s
        self._walk_speed = behavior.walk_speed * unit
        self._jump_up = behavior.jump_up_speed * unit
        self._jump_off = behavior.jump_off_speed * unit
        self._edge_margin = behavior.edge_margin * unit

        self.state = WalkerState.FALL
        self.timer = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self._seg: Surface | None = None       # 지금 서 있는 발판
        self._departed: Surface | None = None  # 방금 떠난 발판 (같은 창에 다시 착지 방지)
        self._edge_dir = 1
        self._jump_planned = False
        self._monitor: Rect | None = None   # 모니터 전체 영역 (벽 판정용)
        self._work: Rect | None = None      # 작업 영역 (공중에서 x 제한용)
        self._works: list[Rect] = []        # 모든 모니터의 작업 영역 (드래그 범위용)

    # ------------------------------------------------------------------ 외부 인터페이스

    def place(self, cx: float, feet_y: float) -> None:
        """위치를 지정하고 낙하 상태로 만든다 (스폰, 드래그 놓기 등)."""
        self.cx = float(cx)
        self.feet_y = float(feet_y)
        self._seg = None
        self._departed = None
        self.vx = 0.0
        self.vy = 0.0
        self._begin(WalkerState.FALL, 0.0)

    def action(self) -> str:
        if self.state is WalkerState.JUMP_OFF:
            return "jump" if self.vy < 0 else "fall"
        return _ACTION_BY_STATE[self.state]

    def is_grounded(self) -> bool:
        return self.state in GROUNDED_STATES

    def is_held(self) -> bool:
        return self.state is WalkerState.HELD

    def hold(self, cx: float, feet_y: float) -> None:
        """드래그 중: 마우스가 준 위치로 옮기고 물리 상태를 멈춘다.

        위치는 그 위치가 속한 모니터의 작업 영역 안에 맞춰 제한한다 (상단은 화면 밖으로 나가지 않게).
        """
        self._seg = None
        self._departed = None
        self.vx = 0.0
        self.vy = 0.0
        work = self._work_at(cx)
        if work is not None:
            half = self.half_width
            lo, hi = work.left + half, work.right - half
            if lo <= hi:
                cx = min(max(cx, lo), hi)
            feet_y = min(max(feet_y, work.top + self.ground_offset), work.bottom)
        self.cx = float(cx)
        self.feet_y = float(feet_y)
        self._begin(WalkerState.HELD, 0.0)

    def _work_at(self, x: float) -> Rect | None:
        """x가 속한 모니터의 작업 영역. 없으면 마지막으로 본 작업 영역."""
        for work in self._works:
            if work.left <= x < work.right:
                return work
        return self._work

    def on_petted(self, seconds: float) -> None:
        """쓰다듬기: 지상에 있으면 제자리에서 멈춘 채 기뻐하는 그림을 보인다."""
        if self.is_grounded():
            self.command("idle", duration=seconds)

    def release(self, vx: float, vy: float) -> None:
        """드래그를 놓는다. 던진 속도(물리 px/s)로 낙하를 시작한다.

        놓는 위치는 hold()에서 이미 작업 영역 안으로 제한됐다.
        """
        if self.state is not WalkerState.HELD:
            return
        self.vx = float(vx)
        self.vy = float(vy)
        if self.vx > 0:
            self.facing = 1
        elif self.vx < 0:
            self.facing = -1
        self._begin(WalkerState.FALL, 0.0)

    def command(self, behavior: str, direction: int = 0, duration: float | None = None) -> bool:
        """지상에서 idle/walk/sit/sleep 중 하나를 시작한다.

        무작위 선택, 테스트, 이후 먹이 찾기 등에서 사용한다.
        지금 상태가 행동 전환이 가능한 상태가 아니면 무시하고 False를 반환한다.
        """
        if behavior not in BEHAVIOR_STATES:
            raise ValueError(f"알 수 없는 행동: {behavior!r}")
        if self.state not in BEHAVIOR_STATES.values():
            return False
        state = BEHAVIOR_STATES[behavior]
        if state is WalkerState.WALK:
            self.facing = direction if direction in (-1, 1) else self._rng.choice((-1, 1))
            lo, hi = self._beh.walk_duration_s
        elif state is WalkerState.IDLE:
            lo, hi = self._beh.idle_duration_s
        elif state is WalkerState.SIT:
            lo, hi = self._beh.sit_duration_s
        else:
            lo, hi = self._beh.sleep_duration_s
        self._begin(state, duration if duration is not None else self._rng.uniform(lo, hi))
        return True

    def update(self, dt: float, world: WorldSnapshot) -> None:
        dt = min(max(dt, 0.0), self._max_step)
        mon = world.monitor_for(self.cx)
        if mon is None:
            return
        self._monitor = mon.rect
        self._work = mon.work
        self._works = [m.work for m in world.monitors]
        surfaces = world.surfaces_on(mon.rect)

        if self.state is WalkerState.HELD:
            return  # 마우스가 위치를 정한다
        if self.state is WalkerState.STARTLED:
            self.timer -= dt
            if self.timer <= 0:
                self._to_fall()
        elif self.state in GROUNDED_STATES:
            self._update_grounded(dt, world, surfaces)
        else:
            self._update_airborne(dt, surfaces)

        if self.state in AIRBORNE_STATES:
            # 작업 표시줄 위로 떨어지지 않도록 작업 영역 안에서만 움직인다
            self._clamp_airborne_x(self._work)

    # ------------------------------------------------------------------ 지상 상태

    def _update_grounded(self, dt: float, world: WorldSnapshot, surfaces: list[Surface]) -> None:
        if not self._track_support(world, surfaces):
            return
        if self.state is WalkerState.LAND:
            self.timer -= dt
            if self.timer <= 0:
                self._enter_idle()
            return
        if self.state is WalkerState.SCARED:
            self.timer -= dt
            if self.timer <= 0:
                self._finish_scared()
            return
        if self.state is WalkerState.WALK:
            self._walk_step(dt)
            if self.state is not WalkerState.WALK:
                return
        self.timer -= dt
        if self.timer <= 0:
            self._choose_next()

    def _track_support(self, world: WorldSnapshot, surfaces: list[Surface]) -> bool:
        """발판을 따라간다. 발판을 잃었으면 상태를 바꾸고 False를 반환한다."""
        seg = self._seg
        if seg is None:
            self._to_fall()
            return False

        if seg.is_floor:
            candidates = [s for s in surfaces if s.is_floor and s.left <= self.cx <= s.right]
        else:
            if not world.has_surface_window(seg.owner):
                # 창이 닫혔거나 최소화/최대화되었다
                self._to_startled()
                return False
            owned = [s for s in surfaces if s.owner == seg.owner]
            if owned:
                # 창이 움직인 만큼 펫도 함께 움직인다
                self.cx += owned[0].owner_left - seg.owner_left
            candidates = [s for s in owned if s.left <= self.cx <= s.right]

        if not candidates:
            self._to_fall()
            return False
        self._attach(min(candidates, key=lambda s: abs(s.y - self.feet_y)))
        return True

    def _walk_limits(self, seg: Surface, mon: Rect) -> tuple[float, float, bool, bool]:
        """(왼쪽 한계, 오른쪽 한계, 왼쪽이 절벽인지, 오른쪽이 절벽인지).

        절벽은 창 발판의 가장자리에만 생긴다. 작업 영역 바닥의 끝은
        작업 표시줄이나 모니터 벽이므로 뛰어내리지 않고 방향만 바꾼다.
        """
        half = self.half_width
        cliff_left = (not seg.is_floor) and seg.left > mon.left
        cliff_right = (not seg.is_floor) and seg.right < mon.right
        left = seg.left + (self._edge_margin if cliff_left else half)
        right = seg.right - (self._edge_margin if cliff_right else half)
        return left, right, cliff_left, cliff_right

    def _walk_step(self, dt: float) -> None:
        seg = self._seg
        mon = self._monitor
        if seg is None or mon is None:
            return
        left, right, cliff_left, cliff_right = self._walk_limits(seg, mon)
        self.cx += self.facing * self._walk_speed * dt
        if self.facing > 0 and self.cx >= right:
            self.cx = right
            self._reach_edge(+1, cliff_right)
        elif self.facing < 0 and self.cx <= left:
            self.cx = left
            self._reach_edge(-1, cliff_left)

    def _reach_edge(self, direction: int, cliff: bool) -> None:
        if not cliff:
            # 모니터 벽이면 뛰어내리지 않고 방향만 바꾼다
            self.facing = -direction
            return
        self._edge_dir = direction
        self.facing = direction
        self.vx = 0.0
        self._begin(WalkerState.SCARED, self._rng.uniform(*self._beh.scared_duration_s))
        self._jump_planned = self._rng.random() < self._beh.jump_off_chance

    def _finish_scared(self) -> None:
        if self._jump_planned:
            self._start_jump(self._edge_dir)
        else:
            self.facing = -self._edge_dir
            self._begin(WalkerState.WALK, self._rng.uniform(*self._beh.walk_duration_s))

    def _choose_next(self) -> None:
        names = list(self._beh.action_weights)
        weights = [self._beh.action_weights[n] for n in names]
        self.command(self._rng.choices(names, weights=weights)[0])

    def _enter_idle(self) -> None:
        self._begin(WalkerState.IDLE, self._rng.uniform(*self._beh.idle_duration_s))

    # ------------------------------------------------------------------ 공중 상태

    def _start_jump(self, direction: int) -> None:
        self._departed = self._seg
        self._seg = None
        self.facing = direction
        self.vx = direction * self._jump_off
        self.vy = -self._jump_up
        self._begin(WalkerState.JUMP_OFF, 0.0)

    def _update_airborne(self, dt: float, surfaces: list[Surface]) -> None:
        old_feet = self.feet_y
        self.vy = min(self.vy + self._gravity * dt, self._max_fall)
        self.feet_y += self.vy * dt
        self.cx += self.vx * dt
        landing = self._find_landing(surfaces, old_feet)
        if landing is not None:
            self._land(landing)

    def _find_landing(self, surfaces: list[Surface], old_feet: float) -> Surface | None:
        best: Surface | None = None
        for s in surfaces:
            if not (s.left <= self.cx <= s.right):
                continue
            # 이번 프레임에 발이 발판 윗변을 지나 내려온 경우만 착지한다
            if s.y < old_feet - self._tolerance or s.y > self.feet_y + self._tolerance:
                continue
            if self._is_departed(s):
                continue
            if best is None or s.y < best.y:
                best = s
        return best

    def _is_departed(self, s: Surface) -> bool:
        departed = self._departed
        return departed is not None and not departed.is_floor and s.owner == departed.owner

    def _land(self, s: Surface) -> None:
        self.feet_y = float(s.y)
        self._attach(s)
        self._departed = None
        self.vx = 0.0
        self.vy = 0.0
        self._begin(WalkerState.LAND, self._landing_s)

    def _clamp_airborne_x(self, area: Rect | None) -> None:
        if area is None:
            return
        lo = area.left + self.half_width
        hi = area.right - self.half_width
        if lo > hi:
            return
        if self.cx < lo or self.cx > hi:
            self.cx = min(max(self.cx, lo), hi)
            self.vx = 0.0

    # ------------------------------------------------------------------ 상태 전환 도우미

    def _attach(self, s: Surface) -> None:
        self._seg = s
        self.feet_y = float(s.y)

    def _to_fall(self) -> None:
        self._departed = self._seg
        self._seg = None
        self.vx = 0.0
        self.vy = 0.0
        self._begin(WalkerState.FALL, 0.0)

    def _to_startled(self) -> None:
        self._departed = None
        self._seg = None
        self.vx = 0.0
        self.vy = 0.0
        self._begin(WalkerState.STARTLED, self._beh.startled_duration_s)

    def _begin(self, state: WalkerState, duration: float) -> None:
        self.state = state
        self.timer = duration
