"""먹이: 떨어지기, 사라지기, 펫이 찾아가 먹기 (Qt/Win32 비의존).

- FoodPool: 화면에 놓인 먹이 목록. 모든 펫이 함께 쓰고, 펫마다 하나씩 골라 먹는다.
  먹이는 중력으로 떨어지거나(sinks 인 먹이는 천천히 가라앉음), 발판 위에 멈춘다.
  lifetime_s(실제 시간)가 지나면 사라진다.
- Feeding: 한 마리 펫의 먹이 찾기. 같은 높이에 있는 먹이를 고르고, 아래 먹이는 가장자리에서
  뛰어내리고, 위 먹이는 올려다보며 낑낑거린다. 도착하면 먹는다.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from core.geometry import Rect, Surface
from core.needs import Needs

if TYPE_CHECKING:
    from pets.base import PetBody


class Reach(enum.Enum):
    REACH = "reach"  # 같은 높이 발판에서 걸어가서 먹을 수 있다
    BELOW = "below"  # 발판보다 아래에 있다 (가장자리에서 뛰어내려야 한다)
    ABOVE = "above"  # 발판보다 위에 있다 (올려다보며 낑낑거린다)
    OUT = "out"      # 닿을 수 없다


_REACHABLE = frozenset({Reach.REACH, Reach.BELOW})


@dataclass
class FoodItem:
    id: int
    kind: str
    x: float          # 가운데 x (물리 px)
    y: float          # 현재 발 기준선 y (물리 px). 떨어지는 중에는 target_y 보다 위
    target_y: float   # 멈출 발판 높이
    sinking: bool = False
    vy: float = 0.0
    age: float = 0.0  # 놓인 뒤 실제 시간(초)
    claimed_by: int | None = None

    @property
    def falling(self) -> bool:
        return self.y < self.target_y - 1e-6


class FoodPool:
    def __init__(
        self,
        *,
        lifetime_s: float,
        max_items: int,
        gravity: float,
        max_fall: float,
        sink_speed: float,
    ) -> None:
        self._lifetime = float(lifetime_s)
        self._max_items = int(max_items)
        self._gravity = float(gravity)
        self._max_fall = float(max_fall)
        self._sink = float(sink_speed)
        self._next_id = 1
        self.items: list[FoodItem] = []

    def drop(
        self, kind: str, x: float, y: float, target_y: float, *, sinking: bool = False
    ) -> FoodItem | None:
        """먹이를 놓는다. 꽉 찼으면 None."""
        if len(self.items) >= self._max_items:
            return None
        item = FoodItem(self._next_id, kind, float(x), float(y), float(target_y), sinking)
        self._next_id += 1
        self.items.append(item)
        return item

    def remove(self, item: FoodItem) -> None:
        if item in self.items:
            self.items.remove(item)

    def clear(self) -> None:
        self.items.clear()

    def step(self, dt: float) -> None:
        dt = max(0.0, dt)
        for item in list(self.items):
            item.age += dt
            if item.falling:
                if item.sinking:
                    item.y = min(item.target_y, item.y + self._sink * dt)
                else:
                    item.vy = min(item.vy + self._gravity * dt, self._max_fall)
                    item.y = min(item.target_y, item.y + item.vy * dt)
            if item.age >= self._lifetime:
                self.remove(item)

    def available(self, pet_id: int, *, include_falling: bool = False) -> list[FoodItem]:
        """이 펫이 고를 수 있는 먹이: 다른 펫이 찜하지 않았고, (헤엄치는 펫이 아니면) 다 떨어진 것."""
        return [
            i for i in self.items
            if (include_falling or not i.falling) and i.claimed_by in (None, pet_id)
        ]


def surface_landing(surfaces: Sequence[Surface], x: float, y: float) -> float | None:
    """x 아래(y 이상)에서 가장 가까운 발판의 높이. 없으면 None."""
    best: float | None = None
    for s in surfaces:
        if s.left <= x <= s.right and s.y >= y - 1e-6 and (best is None or s.y < best):
            best = float(s.y)
    return best


def floor_of(works: Sequence[Rect], x: float) -> float | None:
    """x가 속한 작업 영역의 바닥 높이."""
    for work in works:
        if work.left <= x < work.right:
            return float(work.bottom)
    return float(works[0].bottom) if works else None


class Feeding:
    """한 펫이 먹이를 찾아 먹는 과정. 펫 몸은 PetBody 인터페이스로만 다룬다."""

    def __init__(self, pet_id: int, needs: Needs, pool: FoodPool) -> None:
        self.pet_id = pet_id
        self._needs = needs
        self._pool = pool
        self.target: FoodItem | None = None
        self.whimper = False  # 위에 있는 먹이에 닿지 못해 낑낑거리는 중
        self._eating = False

    def tick(self, body: PetBody, *, paused: bool = False) -> bool:
        """한 단계 진행. 이번 단계에 먹기가 끝났으면 True를 준다."""
        if body.take_meal():
            if self.target is not None:
                self._pool.remove(self.target)
            self._needs.feed()
            self.release(body)
            return True
        if body.is_eating():
            return False
        if self._eating:
            self.release(body)  # 먹는 도중 방해받았다 (들기 등): 다시 찾아간다
        self.whimper = False
        if paused or self._needs.dead or not self._needs.can_eat():
            self.release(body)
            return False
        if self.target is not None and self.target not in self._pool.items:
            self.release(body)
        if self.target is None:
            self.target = self._choose(body)
            if self.target is None:
                self.whimper = self._only_above(body)
                return False
        self.target.claimed_by = self.pet_id
        reach = body.reach_food(self.target.x, self.target.y)
        if reach is Reach.REACH:
            if body.arrived():
                self._eating = body.begin_eat(self._needs.eat_duration_s)
            else:
                body.approach_food(self.target.x, self.target.y)
        elif reach is Reach.BELOW:
            body.approach_drop(self.target.x, self.target.y)
        else:
            self.whimper = reach is Reach.ABOVE
            self.release(body)
        return False

    def release(self, body: PetBody) -> None:
        """먹이 찾기를 그만둔다 (먹이는 남는다)."""
        if self.target is not None and self.target.claimed_by == self.pet_id:
            self.target.claimed_by = None
        if self.target is not None or self._eating:
            body.cancel_walk()
        self.target = None
        self._eating = False

    def _choose(self, body: PetBody) -> FoodItem | None:
        best: FoodItem | None = None
        best_gap = 0.0
        for item in self._pool.available(self.pet_id, include_falling=body.movement == "swimmer"):
            if body.reach_food(item.x, item.y) not in _REACHABLE:
                continue
            gap = abs(item.x - body.cx)
            if best is None or gap < best_gap:
                best, best_gap = item, gap
        return best

    def _only_above(self, body: PetBody) -> bool:
        items = self._pool.items
        return bool(items) and all(body.reach_food(i.x, i.y) is Reach.ABOVE for i in items)
