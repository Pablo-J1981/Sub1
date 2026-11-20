"""펫 한 마리를 보여 주는 창. 물리는 body가, 그림 선택은 이 클래스가 맡는다.

좌표 변환: body는 물리 픽셀 좌표를 쓰고, 창 위치는 SetWindowPos로 직접 옮긴다.
Qt의 move()는 DPI 논리 좌표를 쓰므로 섞어 쓰지 않는다.
마우스 커서 위치도 같은 물리 픽셀 기준(GetCursorPos)으로 읽는다.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMenu

from core.animation import frame_index
from core.mood import Mood
from core.pet_spec import PetSpec
from core.pointer import PetPointer
from pets.base import PetBody
from platform_win.windows import get_cursor_pos, move_window
from ui.overlay_window import OverlayWindow
from ui.sprites import SpriteBank
from ui.world_poller import WorldPoller

log = logging.getLogger("desktop_pet")

# 기분 그림은 몸이 가만히 쉬고 있을 때만 덮어쓴다 (걷는 중에 기쁨 그림이 나오면 어색하다)
_MOOD_OVERRIDE_ACTIONS = frozenset({"idle"})


class PetView(OverlayWindow):
    hideRequested = Signal()
    quitRequested = Signal()

    def __init__(
        self,
        body: PetBody,
        spec: PetSpec,
        sprites: SpriteBank,
        poller: WorldPoller,
        pet_scale: int,
        fps: float,
        mood: Mood,
        pointer: PetPointer,
        cursor: Callable[[], tuple[int, int]] = get_cursor_pos,
    ) -> None:
        super().__init__()
        self._body = body
        self._spec = spec
        self._sprites = sprites
        self._poller = poller
        self._pet_scale = pet_scale
        self._mood = mood
        self._pointer = pointer
        self._cursor = cursor
        self._menu: QMenu | None = None
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
        self._mood.step(dt)
        self._update_pointer(now)
        self._body.update(dt, self._poller.latest)
        self._apply_position()
        self._sync_art(now)

    def finish_drag(self, now: float) -> None:
        """왼쪽 버튼을 뗐을 때. 드래그였다면 던지고 기분을 조금 낮춘다."""
        x, y = self._cursor()
        velocity = self._pointer.release(now, x, y)
        if velocity is not None:
            self._body.release(*velocity)
            self._mood.dropped()

    @property
    def mood(self) -> Mood:
        return self._mood

    # ------------------------------------------------------------------ 마우스 이벤트

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 이름 규칙)
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = self._cursor()
            self._pointer.press(x, y, self._body.cx, self._body.feet_y)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_menu()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.finish_drag(time.perf_counter())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._pointer.hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._pointer.hover(False)
        super().leaveEvent(event)

    # ------------------------------------------------------------------ 내부

    def _update_pointer(self, now: float) -> None:
        x, y = self._cursor()
        result = self._pointer.poll(now, x, y)
        if result.hold is not None:
            self._body.hold(*result.hold)
        if result.petted:
            joy_seconds = self._mood.petted()
            self._body.on_petted(joy_seconds)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        info = menu.addAction(f"기분: {self._mood.label()} ({round(self._mood.value)})")
        info.setEnabled(False)
        menu.addSeparator()
        hide = menu.addAction("펫 숨기기")
        hide.triggered.connect(lambda _checked=False: self.hideRequested.emit())
        quit_action = menu.addAction("종료")
        quit_action.triggered.connect(lambda _checked=False: self.quitRequested.emit())
        self._menu = menu  # 참조를 유지해야 메뉴가 바로 사라지지 않는다
        menu.popup(QCursor.pos())

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

    def _display_action(self) -> str:
        """몸 상태(물리)가 고른 동작에 기분 그림을 덧씌운다."""
        action = self._body.action()
        if action in _MOOD_OVERRIDE_ACTIONS:
            if self._mood.is_joyful and "happy" in self._spec.actions:
                return "happy"
            if self._mood.is_sad and "sad" in self._spec.actions:
                return "sad"
        return action

    def _sync_art(self, now: float) -> None:
        action = self._display_action()
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
