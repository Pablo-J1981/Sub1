"""펫 한 마리를 보여 주는 창. 물리는 body가, 그림 선택은 이 클래스가 맡는다.

좌표 변환: body는 물리 픽셀 좌표를 쓰고, 창 위치는 SetWindowPos로 직접 옮긴다.
Qt의 move()는 DPI 논리 좌표를 쓰므로 섞어 쓰지 않는다.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import Qt, QTimer

from core.animation import frame_index
from core.pet_spec import PetSpec
from pets.base import PetBody
from platform_win.windows import move_window
from ui.overlay_window import OverlayWindow
from ui.sprites import SpriteBank
from ui.world_poller import WorldPoller

log = logging.getLogger("desktop_pet")


class PetView(OverlayWindow):
    def __init__(
        self,
        body: PetBody,
        spec: PetSpec,
        sprites: SpriteBank,
        poller: WorldPoller,
        pet_scale: int,
        fps: float,
    ) -> None:
        super().__init__()
        self._body = body
        self._spec = spec
        self._sprites = sprites
        self._poller = poller
        self._pet_scale = pet_scale
        self._last_now: float | None = None
        self._action: str | None = None
        self._action_started = 0.0
        self._art_key: tuple[str, int, int] | None = None
        self._placed: tuple[int, int] | None = None

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, round(1000 / fps)))
        self._timer.timeout.connect(self._on_timer)

        # 첫 그림을 먼저 설정해 창 크기와 클릭 영역을 만든다
        self._sync_art(0.0)

    # ------------------------------------------------------------------ 외부 인터페이스

    def spawn(self, cx: float, feet_y: float) -> None:
        self._body.place(cx, feet_y)

    def start(self) -> None:
        self._last_now = None
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def advance(self, now: float) -> None:
        """now(초)까지 펫을 진행시킨다. 타이머와 테스트가 함께 쓴다."""
        dt = 0.0 if self._last_now is None else max(0.0, now - self._last_now)
        self._last_now = now
        self._body.update(dt, self._poller.latest)
        self._apply_position()
        self._sync_art(now)

    # ------------------------------------------------------------------ 내부

    def _on_timer(self) -> None:
        try:
            self.advance(time.perf_counter())
        except Exception:  # 한 프레임의 오류로 프로그램이 죽지 않게 한다
            log.exception("펫 갱신 중 오류")

    def _apply_position(self) -> None:
        x = round(self._body.window_left)
        y = round(self._body.window_top)
        if self._placed == (x, y):
            return
        move_window(int(self.winId()), x, y)
        self._placed = (x, y)

    def _sync_art(self, now: float) -> None:
        action = self._body.action()
        if action != self._action:
            self._action = action
            self._action_started = now

        action_spec = self._spec.actions[action]
        index = frame_index(now - self._action_started, action_spec.frames, action_spec.fps)
        facing = self._body.facing
        key = (action, index, facing)
        if key == self._art_key:
            return

        image = self._sprites.frame(action, index)
        if facing < 0:
            # 기본 그림은 오른쪽을 보고 있다. 왼쪽은 좌우 반전한다.
            image = image.flipped(Qt.Orientation.Horizontal)
        self._art_key = key
        self.set_art(image, self._pet_scale)
