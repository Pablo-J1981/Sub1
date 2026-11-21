"""먹이 찾아가서 먹기 (Qt/Win32 비의존).

흐름
1. 사용자가 먹이를 놓으면 먹이 x 위치가 정해진다 (drop).
2. 펫이 바닥(발판이 작업 영역 바닥)에 서 있고 먹이 x가 걸을 수 있는 범위 안이면 걸어간다.
3. 도착하면 eat_duration_s 동안 먹는다 (EAT 상태).
4. 다 먹으면 포만감을 채우고 먹이가 사라진다.

먹는 도중 안거나 들면 먹기가 끝나지 않으므로 먹이는 그대로 남고, 다시 바닥에 서면 다시 간다.
창 위에 있을 때는 바닥으로 내려가지 않는다 (지금은 바닥에 있을 때만 먹이를 찾는다).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.geometry import Rect
from core.needs import Needs

if TYPE_CHECKING:
    from pets.base import PetBody


def food_spot(work: Rect, pet_cx: float, margin: float) -> float:
    """작업 영역 바닥에 먹이 중심을 놓을 x.

    펫에서 먼 쪽 3/4 지점에 두어 펫이 실제로 걸어가서 먹도록 한다.
    margin 만큼 벽에서 떨어뜨린다.
    """
    lo = work.left + margin
    hi = work.right - margin
    mid = (work.left + work.right) / 2
    if lo > hi:
        return mid
    share = 0.75 if pet_cx < mid else 0.25
    return lo + (hi - lo) * share


class Feeding:
    def __init__(self, needs: Needs) -> None:
        self._needs = needs
        self.food_x: float | None = None
        self._eating = False

    @property
    def has_food(self) -> bool:
        return self.food_x is not None

    def drop(self, x: float, body: PetBody) -> bool:
        """먹이를 x 위치에 놓는다. 이미 있던 먹이는 사라진다.

        먹는 중이면 놓지 않고 False를 준다. 걷는 중이면 새 먹이 쪽으로 방향을 바꾼다.
        """
        if body.is_eating():
            return False
        body.cancel_walk()
        self.food_x = float(x)
        self._eating = False
        return True

    def clear(self) -> None:
        self.food_x = None
        self._eating = False

    def tick(self, body: PetBody, *, paused: bool = False) -> bool:
        """한 단계 진행한다. 이번 단계에 먹이를 다 먹었으면 True.

        paused: 쓰다듬는 중 등 먹이 쪽으로 가지 않을 때 True.
        """
        if self.food_x is None:
            return False
        if body.take_meal():
            self._needs.feed()
            self.clear()
            return True
        if self._eating:
            if not body.is_eating():
                self._eating = False  # 먹는 도중 방해받았다 (들기 등). 다시 찾아간다.
            return False
        if paused:
            return False
        if body.arrived():
            self._eating = body.begin_eat(self._needs.eat_duration_s)
            return False
        if self._can_reach(body, self.food_x):
            body.walk_to(self.food_x)
        return False

    @staticmethod
    def _can_reach(body: PetBody, x: float) -> bool:
        surface = body.ground_surface()
        reach = body.reach_range()
        if surface is None or not surface.is_floor or reach is None:
            return False
        return reach[0] <= x <= reach[1]
