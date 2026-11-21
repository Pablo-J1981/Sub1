"""펫 한 마리를 보여 주는 창. 물리는 body가, 그림 선택은 이 클래스가 맡는다.

좌표 변환: body는 물리 픽셀 좌표를 쓰고, 창 위치는 SetWindowPos로 직접 옮긴다.
Qt의 move()는 DPI 논리 좌표를 쓰므로 섞어 쓰지 않는다.
마우스 커서 위치도 같은 물리 픽셀 기준(GetCursorPos)으로 읽는다.

시간 배속(time_scale)은 펫 안의 시간(움직임, 기분, 포만감, 먹기)에만 적용한다.
마우스 입력과 그림 넘김은 실제 시간을 쓴다.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QImage
from PySide6.QtWidgets import QMenu

from core.animation import frame_index, frame_index_once
from core.feeding import Feeding, food_spot
from core.mood import Mood
from core.needs import Needs
from core.pet_spec import PetSpec
from core.pointer import PetPointer
from pets.base import PetBody
from platform_win.windows import get_cursor_pos, move_window
from ui.item_view import ItemView
from ui.overlay_window import OverlayWindow
from ui.sprites import SpriteBank
from ui.world_poller import WorldPoller

log = logging.getLogger("desktop_pet")

# 기분/배고픔 그림은 몸이 가만히 쉬고 있을 때만 덮어쓴다 (걷는 중에 그런 그림이 나오면 어색하다)
_OVERRIDE_ACTIONS = frozenset({"idle"})
# 한 번 재생하고 마지막 그림에서 멈추는 동작
_HOLD_LAST = frozenset({"die"})
_DEATH_ACTION = "die"
_TOMB = "tomb"
# 실제 시간 한 번에 진행시킬 최대 길이(초). 창이 멈췄다 풀릴 때 한꺼번에 튀지 않게 한다.
_MAX_REAL_STEP_S = 0.25


class PetView(OverlayWindow):
    hideRequested = Signal()
    quitRequested = Signal()
    restartRequested = Signal()

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
        needs: Needs,
        *,
        food_image: QImage | None = None,
        time_scale: float = 1.0,
        max_step_s: float = 0.1,
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
        self._needs = needs
        self._feeding = Feeding(needs)
        self._time_scale = float(time_scale)
        self._max_step = float(max_step_s)
        self._cursor = cursor
        self._menu: QMenu | None = None
        self._last_now: float | None = None
        self._action: str | None = None
        self._action_started = 0.0
        self._art_key: tuple[str, int, int] | None = None
        self._placed: tuple[int, int] | None = None
        self._death_at: float | None = None
        self._food_view: ItemView | None = None
        if food_image is not None:
            self._food_view = ItemView(food_image, pet_scale)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, round(1000 / fps)))
        self._timer.timeout.connect(self._on_timer)

        # 첫 그림을 먼저 설정해 창 크기와 클릭 영역을 만든다
        self._sync_art(0.0)

    # ------------------------------------------------------------------ 외부 인터페이스

    def spawn(self, cx: float, feet_y: float) -> None:
        self._body.place(cx, feet_y)

    def restart(self, cx: float, feet_y: float) -> None:
        """사망 후 다시 시작: 살아 있는 상태, 처음 기분과 포만감, 처음 위치."""
        self._needs.revive()
        self._mood.reset()
        self._death_at = None
        self._feeding.clear()
        if self._food_view is not None:
            self._food_view.hide_item()
        self._body.set_frozen(False)
        self._body.place(cx, feet_y)
        self._action = None
        self._art_key = None

    def start(self) -> None:
        self._last_now = None
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def advance(self, now: float) -> None:
        """now(초)까지 펫을 진행시킨다. 타이머와 테스트가 함께 쓴다."""
        real_dt = 0.0 if self._last_now is None else max(0.0, now - self._last_now)
        self._last_now = now
        real_dt = min(real_dt, _MAX_REAL_STEP_S)
        sim_dt = real_dt * self._time_scale  # 펫 안에서 흐르는 시간

        self._step_needs(sim_dt, now)
        self._mood.step(sim_dt)
        self._update_pointer(now)
        self._step_body(sim_dt)
        self._step_feeding()
        self._apply_position()
        self._sync_art(now)

    def feed(self) -> bool:
        """먹이를 바닥에 놓는다. 펫이 먹을 수 있으면 True."""
        if self._food_view is None or self._needs.dead or self._body.is_eating():
            return False
        floor = self._body.floor_rect()
        if floor is None:
            return False
        food_w, food_h = self._food_view.physical_size()
        x = food_spot(floor, self._body.cx, food_w / 2)
        if not self._feeding.drop(x, self._body):
            return False
        self._food_view.show_at(x - food_w / 2, floor.bottom - food_h)
        return True

    def finish_drag(self, now: float) -> None:
        """왼쪽 버튼을 뗐을 때. 드래그였다면 던지고 기분을 조금 낮춘다."""
        x, y = self._cursor()
        velocity = self._pointer.release(now, x, y)
        if self._needs.dead:
            # 죽은 뒤에도 들고 있었다면 제자리에 떨어뜨린다 (그대로 떠 있으면 안 된다)
            if self._body.is_held():
                self._body.release(0.0, 0.0)
            return
        if velocity is not None:
            self._body.release(*velocity)
            self._mood.dropped()

    @property
    def mood(self) -> Mood:
        return self._mood

    @property
    def needs(self) -> Needs:
        return self._needs

    # ------------------------------------------------------------------ 마우스 이벤트

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 이름 규칙)
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._needs.dead:
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

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._food_view is not None:
            self._food_view.set_allowed(True)

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        if self._food_view is not None:
            self._food_view.set_allowed(False)  # 펫을 숨기면 먹이도 함께 숨긴다

    # ------------------------------------------------------------------ 내부: 시간 진행

    def _step_needs(self, sim_dt: float, now: float) -> None:
        was_dead = self._needs.dead
        self._needs.step(sim_dt)
        if self._needs.dead and not was_dead:
            self._body.set_frozen(True)
            self._death_at = now
            self._feeding.clear()
            if self._food_view is not None:
                self._food_view.hide_item()
            log.info("펫이 사망했습니다.")

    def _step_body(self, sim_dt: float) -> None:
        # 몸 계산은 max_step 단위로 나눠 돌린다 (배속이 커도 발판을 뚫지 않게)
        world = self._poller.latest
        remaining = sim_dt
        while remaining > 1e-9:
            step = min(remaining, self._max_step)
            self._body.update(step, world)
            remaining -= step

    def _step_feeding(self) -> None:
        # 들고 있을 때, 죽었을 때, 쓰다듬어 기뻐하는 동안에는 먹이 쪽으로 가지 않는다
        paused = self._body.is_held() or self._needs.dead or self._mood.is_joyful
        self._feeding.tick(self._body, paused=paused)
        if not self._feeding.has_food and self._food_view is not None:
            self._food_view.hide_item()

    def _update_pointer(self, now: float) -> None:
        x, y = self._cursor()
        result = self._pointer.poll(now, x, y)
        if self._needs.dead:
            return  # 죽은 몸은 들거나 쓰다듬을 수 없다
        if result.hold is not None:
            self._body.hold(*result.hold)
        if result.petted:
            joy_seconds = self._mood.petted()
            self._body.on_petted(joy_seconds)

    # ------------------------------------------------------------------ 내부: 메뉴와 그림

    def _show_menu(self) -> None:
        menu = QMenu(self)
        mood_info = menu.addAction(f"기분: {self._mood.label()} ({round(self._mood.value)})")
        mood_info.setEnabled(False)
        hunger_info = menu.addAction(
            f"포만감: {self._needs.label()} ({round(self._needs.fullness)})"
        )
        hunger_info.setEnabled(False)
        menu.addSeparator()
        if self._needs.dead:
            restart = menu.addAction("다시 시작")
            restart.triggered.connect(lambda _checked=False: self.restartRequested.emit())
        else:
            feed = menu.addAction("먹이 주기")
            feed.setEnabled(self._food_view is not None and not self._body.is_eating())
            feed.triggered.connect(lambda _checked=False: self.feed())
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
        """몸 상태(물리)가 고른 동작에 기분과 배고픔 그림을 덧씌운다."""
        action = self._body.action()
        if action not in _OVERRIDE_ACTIONS:
            return action
        actions = self._spec.actions
        if self._mood.is_joyful and "happy" in actions:
            return "happy"
        if self._needs.is_starving() and "sick" in actions:
            return "sick"
        if self._needs.is_hungry() and "hungry" in actions:
            return "hungry"
        if self._mood.is_sad and "sad" in actions:
            return "sad"
        return action

    def _sync_art(self, now: float) -> None:
        if self._needs.dead:
            if self._death_at is None:
                self._death_at = now  # 사망 판정이 이 창 밖에서 일어나도 시작 시각을 잡는다
            die_spec = self._spec.actions[_DEATH_ACTION]
            if now - self._death_at >= die_spec.frames / die_spec.fps:
                self._show_art(_TOMB, 0, self._sprites.tomb())
                return
            action = _DEATH_ACTION
        else:
            action = self._display_action()

        if action != self._action:
            self._action = action
            self._action_started = now

        action_spec = self._spec.actions[action]
        elapsed = now - self._action_started
        if action in _HOLD_LAST:
            index = frame_index_once(elapsed, action_spec.frames, action_spec.fps)
        else:
            index = frame_index(elapsed, action_spec.frames, action_spec.fps)
        self._show_art(action, index, self._sprites.frame(action, index))

    def _show_art(self, name: str, index: int, image: QImage) -> None:
        facing = self._body.facing
        key = (name, index, facing)
        if key == self._art_key:
            return
        if facing < 0:
            # 기본 그림은 오른쪽을 보고 있다. 왼쪽은 좌우 반전한다.
            image = image.flipped(Qt.Orientation.Horizontal)
        self._art_key = key
        self.set_art(image, self._pet_scale)
