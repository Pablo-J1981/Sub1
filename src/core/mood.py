"""기분 수치 (0~100). 쓰다듬기, 들었다 놓기, 시간에 따른 회복을 담당한다.

Qt/Win32 비의존. 수치는 모두 config의 mood 항목에서 온다.
기분은 지금은 메모리에만 있으며, 저장은 5단계에서 추가한다.
"""

from __future__ import annotations

from core.config import MoodConfig

NEUTRAL = 50.0
GOOD_FROM = 70.0  # 이 값 이상이면 "좋음"


class Mood:
    def __init__(self, cfg: MoodConfig) -> None:
        self._cfg = cfg
        self.value = float(cfg.start)
        self.joy_left = 0.0  # 기뻐하는 그림을 보일 남은 시간(초)

    def step(self, dt: float) -> None:
        """시간이 흐르면 기분은 중립(50)으로 천천히 돌아온다."""
        dt = max(0.0, dt)
        rate = self._cfg.decay_per_s * dt
        if self.value > NEUTRAL:
            self.value = max(NEUTRAL, self.value - rate)
        elif self.value < NEUTRAL:
            self.value = min(NEUTRAL, self.value + rate)
        self.joy_left = max(0.0, self.joy_left - dt)

    def reset(self) -> None:
        """다시 시작할 때 처음 기분으로 되돌린다."""
        self.value = float(self._cfg.start)
        self.joy_left = 0.0

    def petted(self) -> float:
        """쓰다듬기 한 번. 기뻐할 시간(초)을 돌려준다."""
        self.value = min(100.0, self.value + self._cfg.pet_gain)
        self.joy_left = self._cfg.pet_joy_duration_s
        return self.joy_left

    def dropped(self) -> None:
        self.value = max(0.0, self.value - self._cfg.drop_penalty)

    @property
    def is_joyful(self) -> bool:
        return self.joy_left > 0

    @property
    def is_sad(self) -> bool:
        return self.value <= self._cfg.sad_below

    def label(self) -> str:
        if self.is_sad:
            return "나쁨"
        if self.value >= GOOD_FROM:
            return "좋음"
        return "보통"
