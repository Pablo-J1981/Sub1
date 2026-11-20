"""마우스 입력 판정 (Qt/Win32 비의존).

- ThrowTracker: 놓을 때의 던지기 속도를 최근 구간 기준으로 계산한다.
- throw_velocity: 관성 배율과 속도 상한을 적용한다.
- StrokeDetector: 쓰다듬기 한 번(좌우 왕복)을 센다.

좌표는 모두 물리 픽셀 기준이다.
"""

from __future__ import annotations

import math
from collections import deque


class ThrowTracker:
    """최근 window_s 초 동안의 커서 위치로 속도를 추정한다."""

    def __init__(self, window_s: float) -> None:
        self._window = window_s
        self._samples: deque[tuple[float, float, float]] = deque()  # (시각, x, y)

    def clear(self) -> None:
        self._samples.clear()

    def add(self, t: float, x: float, y: float) -> None:
        self._samples.append((t, x, y))
        while len(self._samples) > 1 and t - self._samples[0][0] > self._window:
            self._samples.popleft()

    def velocity(self, now: float) -> tuple[float, float]:
        """now 기준 최근 window_s 초 동안의 평균 속도(px/s).

        구간 안에 샘플이 두 개 미만이면 0. 놓기 직전에 멈춰 있었다면
        구간 안의 위치 변화가 작아 자연스럽게 속도가 줄어든다.
        """
        recent = [s for s in self._samples if now - s[0] <= self._window]
        if len(recent) < 2:
            return (0.0, 0.0)
        t0, x0, y0 = recent[0]
        t1, x1, y1 = recent[-1]
        dt = t1 - t0
        if dt <= 0:
            return (0.0, 0.0)
        return ((x1 - x0) / dt, (y1 - y0) / dt)


def throw_velocity(
    vx: float, vy: float, inertia: float, max_speed: float
) -> tuple[float, float]:
    """관성 배율을 곱하고 속도 상한을 넘지 않도록 줄인다."""
    vx *= inertia
    vy *= inertia
    speed = math.hypot(vx, vy)
    if speed > max_speed and speed > 0:
        scale = max_speed / speed
        vx *= scale
        vy *= scale
    return vx, vy


class StrokeDetector:
    """쓰다듬기 횟수를 센다.

    방향이 바뀔 때, 직전 방향으로 min_travel 이상 움직였다면 한 번으로 센다.
    떨림이나 조금씩 움직이는 것은 세지 않는다.
    """

    def __init__(self, min_travel: float) -> None:
        self._min = min_travel
        self._last_x: float | None = None
        self._dir = 0
        self._run_start = 0.0

    def reset(self) -> None:
        self._last_x = None
        self._dir = 0
        self._run_start = 0.0

    def feed(self, x: float) -> bool:
        """커서 x를 넣는다. 이번 샘플로 쓰다듬기 한 번이 완성되었으면 True."""
        if self._last_x is None:
            self._last_x = x
            return False
        dx = x - self._last_x
        if dx == 0:
            return False
        direction = 1 if dx > 0 else -1
        completed = False
        if self._dir == 0:
            self._dir = direction
            self._run_start = self._last_x
        elif direction != self._dir:
            if abs(self._last_x - self._run_start) >= self._min:
                completed = True
            self._dir = direction
            self._run_start = self._last_x
        self._last_x = x
        return completed


class PollResult:
    """poll()의 결과. hold는 드래그 중 펫을 둘 물리 좌표, petted는 쓰다듬기 한 번 완성 여부."""

    __slots__ = ("hold", "petted")

    def __init__(self, hold: tuple[float, float] | None = None, petted: bool = False) -> None:
        self.hold = hold
        self.petted = petted


class PetPointer:
    """펫 하나의 마우스 상태 (드래그, 던지기, 쓰다듬기). Qt/Win32 비의존.

    사용 순서
    - 왼쪽 버튼 누름: press(x, y, cx, feet_y)
    - 매 프레임: poll(now, x, y) -> 드래그 위치 또는 쓰다듬기 여부
    - 버튼 뗌: release(now, x, y) -> 던질 속도(드래그였을 때만)
    - 커서가 펫 위에 들어오거나 나감: hover(inside)
    """

    def __init__(
        self,
        *,
        drag_threshold: float,
        min_stroke: float,
        throw_inertia: float,
        max_throw_speed: float,
        velocity_window_s: float,
    ) -> None:
        self._threshold = drag_threshold
        self._inertia = throw_inertia
        self._max_speed = max_throw_speed
        self._tracker = ThrowTracker(velocity_window_s)
        self._stroke = StrokeDetector(min_stroke)
        self.pressed = False
        self.dragging = False
        self.hovering = False
        self._press_xy = (0.0, 0.0)
        self._grab = (0.0, 0.0)  # 펫 중심/발 위치 - 누른 커서 위치

    def press(self, x: float, y: float, cx: float, feet_y: float) -> None:
        self.pressed = True
        self.dragging = False
        self._press_xy = (x, y)
        self._grab = (cx - x, feet_y - y)
        self._stroke.reset()

    def hover(self, inside: bool) -> None:
        self.hovering = inside
        if not inside:
            self._stroke.reset()

    def poll(self, now: float, x: float, y: float) -> PollResult:
        if self.pressed:
            if not self.dragging:
                dx = x - self._press_xy[0]
                dy = y - self._press_xy[1]
                if math.hypot(dx, dy) < self._threshold:
                    return PollResult()
                self.dragging = True
                self._tracker.clear()
            self._tracker.add(now, x, y)
            return PollResult(hold=(x + self._grab[0], y + self._grab[1]))
        if self.hovering and self._stroke.feed(x):
            return PollResult(petted=True)
        return PollResult()

    def release(self, now: float, x: float, y: float) -> tuple[float, float] | None:
        """버튼을 뗀다. 드래그였다면 던질 속도(물리 px/s)를, 아니면 None을 준다."""
        was_dragging = self.dragging
        self.pressed = False
        self.dragging = False
        self._stroke.reset()
        if not was_dragging:
            self._tracker.clear()
            return None
        self._tracker.add(now, x, y)
        vx, vy = self._tracker.velocity(now)
        self._tracker.clear()
        return throw_velocity(vx, vy, self._inertia, self._max_speed)
