"""포만감과 배고픔 타이머 (Qt/Win32 비의존).

모든 시간 인자는 '활성 사용 시간(초)'이다 (프로그램 실행 중 + 마지막 입력이 idle_pause_s 안).
- 포만감은 활성 시간 1시간당 decay_per_hour 씩 줄어든다. 숨김 상태여도 줄어든다.
- 포만감이 hungry_below 이하가 되면 배고픔 타이머가 돈다. 숨김 상태에서는 멈춘다.
- 타이머가 critical_hours 가 되면 위독, death_hours 가 되면 사망.
- 먹으면 포만감이 food_amount 만큼 차고 타이머는 0으로 돌아간다.
- 포만감이 eat_refuse_at 이상이면 먹지 않는다.
"""

from __future__ import annotations

from core.config import NeedsConfig

HOUR_S = 3600.0
FULL_LABEL_FROM = 80.0  # 배부름 표시 기준 (eat_refuse_at 과 같은 값으로 쓴다)


class Needs:
    def __init__(
        self,
        cfg: NeedsConfig,
        *,
        fullness: float | None = None,
        hunger_s: float = 0.0,
        dead: bool = False,
    ) -> None:
        self._cfg = cfg
        self.fullness = float(cfg.start if fullness is None else fullness)
        self.hunger_s = float(hunger_s)
        self.dead = bool(dead)

    @property
    def critical_s(self) -> float:
        return self._cfg.critical_hours * HOUR_S

    @property
    def death_s(self) -> float:
        return self._cfg.death_hours * HOUR_S

    @property
    def eat_duration_s(self) -> float:
        return self._cfg.eat_duration_s

    def step(self, active_dt: float, *, hidden: bool = False) -> None:
        """active_dt: 이번 단계의 활성 사용 시간(초). 활성이 아니면 0을 넘긴다."""
        if self.dead or active_dt <= 0:
            return
        thr = self._cfg.hungry_below
        decay = self._cfg.decay_per_hour
        start = self.fullness
        end = max(0.0, start - decay * active_dt / HOUR_S)
        self.fullness = end
        if hidden or end > thr:
            return
        if start <= thr or decay <= 0:
            counted = active_dt
        else:
            # 포만감이 hungry_below 에 닿은 순간부터만 타이머를 센다.
            cross_s = (start - thr) / decay * HOUR_S
            counted = max(0.0, active_dt - cross_s)
        self.hunger_s += counted
        if self.hunger_s >= self.death_s:
            self.dead = True

    def feed(self) -> None:
        self.fullness = min(100.0, self.fullness + self._cfg.food_amount)
        self.hunger_s = 0.0

    def can_eat(self) -> bool:
        return not self.dead and self.fullness < self._cfg.eat_refuse_at

    def is_hungry(self) -> bool:
        return not self.dead and self.fullness <= self._cfg.hungry_below

    def is_critical(self) -> bool:
        return not self.dead and self.hunger_s >= self.critical_s

    def label(self) -> str:
        if self.dead:
            return "사망"
        if self.is_critical():
            return "위독"
        if self.is_hungry():
            return "배고픔"
        if self.fullness >= FULL_LABEL_FROM:
            return "배부름"
        return "보통"
