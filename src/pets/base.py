"""모든 동물의 공통 베이스 (Qt 비의존).

좌표는 물리 픽셀 기준이다.
- cx: 몸통 중심 x
- feet_y: 발이 닿는 y (걷는 펫은 발판 윗변, 헤엄치는 펫은 몸의 기준선)
- ground_offset: 창 윗변에서 feet_y 까지 거리 (그림에서 발 위치로 계산)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.feeding import Reach
from core.geometry import Rect
from core.world import WorldSnapshot


class PetBody(ABC):
    movement: str = ""

    def __init__(self, *, width: float, ground_offset: float, unit: float, below: float = 0.0) -> None:
        if unit <= 0:
            raise ValueError("unit 은 0보다 커야 합니다.")
        self.width = float(width)
        self.ground_offset = float(ground_offset)
        self.below = float(below)  # 발 기준선 아래로 그림이 더 있는 높이 (헤엄치는 펫의 바닥 판정용)
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

    def resize(self, width: float, ground_offset: float, below: float = 0.0) -> None:
        """성장으로 그림 크기가 바뀔 때 (속도 단위 unit 은 그대로)."""
        self.width = float(width)
        self.ground_offset = float(ground_offset)
        self.below = float(below)

    def place(self, cx: float, feet_y: float) -> None:
        """처음 놓거나 다시 놓는다."""
        self.cx = float(cx)
        self.feet_y = float(feet_y)

    @abstractmethod
    def update(self, dt: float, world: WorldSnapshot) -> None:
        """dt초 동안 세계 상태에 맞춰 한 단계 움직인다."""

    @abstractmethod
    def action(self) -> str:
        """지금 보여 줄 동작 이름 (pet.json의 actions 키)."""

    @abstractmethod
    def is_grounded(self) -> bool:
        """발판 위에 서 있거나 걷는 중인지 (공중, 드래그 중이면 False)."""

    @abstractmethod
    def hold(self, cx: float, feet_y: float) -> None:
        """드래그 중: 마우스가 준 위치로 옮기고 물리 계산을 멈춘다."""

    @abstractmethod
    def release(self, vx: float, vy: float) -> None:
        """드래그를 놓는다. (vx, vy)는 던지는 속도(물리 px/s)다."""

    @abstractmethod
    def on_petted(self, seconds: float) -> None:
        """쓰다듬기: 가능하면 잠시 멈추고 기뻐하는 시간을 준다."""

    def pin(self, cx: float, feet_y: float) -> None:
        """무덤처럼 제자리에 고정한다 (물리 없이 그 자리에 머문다)."""
        self.cx = float(cx)
        self.feet_y = float(feet_y)

    def settled(self) -> bool:
        """죽은 뒤 제자리에 완전히 가라앉았는지 (무덤을 세울 수 있는지)."""
        return True

    def observe_cursor(self, x: float, y: float, speed: float) -> None:
        """커서 위치와 속도(물리 px/s)를 알려 준다. 필요한 펫만 쓴다."""

    # 먹이, 장난감 관련 기본값. 이동 타입이 지원할 때만 재정의한다.
    def reach_food(self, x: float, y: float) -> Reach:
        """(x, y) 에 있는 먹이에 닿을 수 있는지."""
        return Reach.OUT

    def approach_food(self, x: float, y: float) -> None:
        """먹이 쪽으로 걸어가거나 헤엄쳐 간다."""

    def approach_drop(self, x: float, y: float) -> None:
        """먹이가 발판보다 아래에 있을 때: 가장자리까지 가서 뛰어내린다."""

    def arrived(self) -> bool:
        """목표 위치에 도착해 먹기를 기다리는지."""
        return False

    def begin_eat(self, duration: float) -> bool:
        """도착한 자리에서 먹기를 시작한다."""
        return False

    def is_eating(self) -> bool:
        """지금 먹는 중인지."""
        return False

    def is_held(self) -> bool:
        """드래그로 들려 있는지."""
        return False

    def take_meal(self) -> bool:
        """먹기가 끝났는지 한 번만 알려 준다."""
        return False

    def cancel_walk(self) -> None:
        """걷기 목표를 버린다."""

    def set_frozen(self, frozen: bool) -> None:
        """True면 제자리에 멈춘다 (사망). False면 다시 움직인다."""

    def ground_surface(self):  # -> Surface | None
        return None

    def floor_rect(self) -> Rect | None:
        return None

    def reach_range(self) -> tuple[float, float] | None:
        return None

    def walk_to(self, x: float) -> bool:
        return False
