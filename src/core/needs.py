"""포만감과 생존 상태 (0~100, Qt/Win32 비의존).

- 시간이 지나면 포만감이 줄어든다.
- 포만감이 0인 상태가 starve_death_s 동안 이어지면 사망한다.
- 먹이를 먹으면 food_amount 만큼 찬다.

수치는 모두 config의 needs 항목에서 온다. 저장은 5단계에서 추가한다.
"""

from __future__ import annotations

from core.config import NeedsConfig

FULL_FROM = 70.0  # 이 값 이상이면 "배부름"


class Needs:
    def __init__(self, cfg: NeedsConfig) -> None:
        self._cfg = cfg
        self.fullness = float(cfg.start)
        self.dead = False
        self._starving_s = 0.0

    @property
    def eat_duration_s(self) -> float:
        return self._cfg.eat_duration_s

    def step(self, dt: float) -> None:
        if self.dead:
            return
        dt = max(0.0, dt)
        self.fullness = max(0.0, self.fullness - self._cfg.decay_per_s * dt)
        if self.fullness <= 0.0:
            self._starving_s += dt
            if self._starving_s >= self._cfg.starve_death_s:
                self.dead = True
        else:
            self._starving_s = 0.0

    def feed(self) -> None:
        self.fullness = min(100.0, self.fullness + self._cfg.food_amount)
        self._starving_s = 0.0

    def revive(self) -> None:
        self.fullness = float(self._cfg.start)
        self.dead = False
        self._starving_s = 0.0

    def is_starving(self) -> bool:
        return not self.dead and self.fullness <= 0.0

    def is_hungry(self) -> bool:
        return not self.dead and self.fullness < self._cfg.hungry_below

    def label(self) -> str:
        if self.dead:
            return "사망"
        if self.is_starving():
            return "굶주림"
        if self.is_hungry():
            return "배고픔"
        if self.fullness >= FULL_FROM:
            return "배부름"
        return "보통"
