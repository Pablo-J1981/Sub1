"""펫 한 마리를 보여 주는 창. 물리는 body가, 상태는 PetRecord가 맡는다.

좌표: body와 창 위치는 물리 픽셀 기준이며 SetWindowPos로 옮긴다 (Qt move()는 쓰지 않는다).
시간: 펫 안의 움직임, 기분, 먹기는 시간 배속을 곱한다. 활성 사용 시간(성장, 포만감, 함께한 시간)은
      실제 시간으로 재고, 활성 여부는 app이 알려 준다. 마우스 입력과 그림 넘김은 실제 시간을 쓴다.
상태: 모든 값은 공유 PetRecord 에 써 넣는다 (저장은 app이 한다).
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter

from core.animation import frame_index, frame_index_once
from core.config import AppConfig
from core.feeding import Feeding, FoodPool
from core.growth import pixel_scale_for, stage_for
from core.mood import Mood
from core.needs import Needs
from core.pet_spec import PetSpec
from core.pointer import PetPointer
from core.records import PetRecord, format_active
from core.render_math import physical_scale
from core.toy import BallToy
from pets.base import PetBody
from platform_win.windows import get_cursor_pos, move_window
from ui.overlay_window import OverlayWindow
from ui.sprites import SpriteBank
from ui.world_poller import WorldPoller

log = logging.getLogger("desktop_pet")

_OVERRIDE_ACTIONS = frozenset({"idle", "swim"})  # 기분/배고픔 그림으로 덮어쓸 수 있는 동작
_HOLD_LAST = frozenset({"die"})                 # 한 번 재생하고 마지막 그림에서 멈추는 동작
_DEATH = "die"
_TOMB = "tomb"
_MAX_REAL_STEP_S = 0.25                         # 창이 멈췄다 풀릴 때 한꺼번에 튀지 않게
_GROW_S = 2.0                                   # 성장 연출 시간 (실제 시간)


class PetView(OverlayWindow):
    noticed = Signal(str)              # 트레이 알림으로 보낼 말
    buried = Signal(object)            # 죽어서 가라앉은 뒤 (PetView 자신)
    contextRequested = Signal(object)  # 오른쪽 클릭 (PetView 자신)

    def __init__(
        self,
        record: PetRecord,
        body: PetBody,
        spec: PetSpec,
        sprites: SpriteBank,
        poller: WorldPoller,
        cfg: AppConfig,
        pointer: PetPointer,
        pool: FoodPool,
        toy: BallToy | None,
        *,
        dpr: float = 1.0,
        status: Callable[[], tuple[bool, bool]] | None = None,
        cursor: Callable[[], tuple[int, int]] = get_cursor_pos,
    ) -> None:
        super().__init__()
        self.record = record
        self._body = body
        self._spec = spec
        self._sprites = sprites
        self._poller = poller
        self._cfg = cfg
        self._pointer = pointer
        self._toy = toy
        self._dpr = float(dpr)
        self._status = status or (lambda: (True, False))
        self._cursor = cursor
        self._time_scale = cfg.debug.time_scale
        self._max_step = cfg.physics.max_step_s

        self._needs = Needs(
            cfg.needs, fullness=record.fullness, hunger_s=record.hunger_s, dead=record.dead
        )
        self._mood = Mood(cfg.mood)
        self._mood.value = float(record.mood)
        self._feeding = Feeding(record.id, self._needs, pool)
        self.stage = record.stage
        self._grow_left = 0.0
        self._critical_sent = self._needs.is_critical()
        self._death_at: float | None = None
        self._buried = record.dead
        self._tip = ""
        self._last_now: float | None = None
        self._action: str | None = None
        self._action_started = 0.0
        self._art_key: tuple | None = None
        self._placed: tuple[int, int] | None = None
        self._input_enabled = True
        self._resize_body()
        if record.dead:
            body.set_frozen(True)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, round(1000 / cfg.display.animation_fps)))
        self._timer.timeout.connect(self._on_timer)

        self._sync_art(0.0)  # 첫 그림을 먼저 설정해 창 크기와 클릭 영역을 만든다

    # ------------------------------------------------------------------ 외부 인터페이스

    @property
    def body(self) -> PetBody:
        return self._body

    @property
    def needs(self) -> Needs:
        return self._needs

    @property
    def mood(self) -> Mood:
        return self._mood

    @property
    def dead(self) -> bool:
        return self._needs.dead

    @property
    def buried_done(self) -> bool:
        return self._buried

    def set_input_enabled(self, enabled: bool) -> None:
        """먹이/공을 놓는 중에는 펫을 누르거나 끌 수 없게 한다."""
        self._input_enabled = bool(enabled)

    def spawn(self, cx: float, feet_y: float) -> None:
        self._body.place(cx, feet_y)

    def start(self) -> None:
        self._last_now = None
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def advance(self, now: float, *, active: bool = True, hidden: bool = False) -> None:
        """now(초)까지 펫을 진행시킨다.

        active: 활성 사용 중인지 (마지막 입력이 idle_pause_s 이내). 활성 시간만 쌓인다.
        hidden: 펫을 숨겼는지. 배고픔 타이머만 멈추고, 포만감 감소와 나머지는 계속된다.
        """
        real_dt = 0.0 if self._last_now is None else max(0.0, now - self._last_now)
        self._last_now = now
        real_dt = min(real_dt, _MAX_REAL_STEP_S)
        sim_dt = real_dt * self._time_scale

        was_dead = self._needs.dead
        active_dt = sim_dt if (active and not was_dead) else 0.0
        self.record.active_s += active_dt
        self._needs.step(active_dt, hidden=hidden)
        if self._needs.dead and not was_dead:
            self._on_death(now)
        self._check_critical()
        self._mood.step(sim_dt)
        self._grow_left = max(0.0, self._grow_left - real_dt)
        self._check_growth(now)

        self._update_pointer(now)
        self._step_body(sim_dt)
        paused = (
            self._body.is_held() or self._needs.dead or self._mood.is_joyful or self._grow_left > 0
        )
        if self._feeding.tick(self._body, paused=paused):
            self.record.meals += 1
        self._step_toy(paused)
        self._apply_position()
        self._sync_art(now)
        self._write_back()

    def finish_drag(self, now: float) -> None:
        """왼쪽 버튼을 뗐을 때. 살아 있으면 던지고 기분을 낮춘다. 죽었으면 제자리에 놓는다."""
        x, y = self._cursor()
        velocity = self._pointer.release(now, x, y)
        if self._needs.dead:
            if self._body.is_held():
                self._body.release(0.0, 0.0)
            return
        if velocity is not None:
            self._body.release(*velocity)
            self._mood.dropped()

    def info_text(self) -> str:
        """상태 보기 내용. 함께한 시간은 활성 사용 시간이다."""
        r = self.record
        return (
            f"이름: {r.name}\n"
            f"단계: {self.stage} / 5\n"
            f"포만감: {self._needs.label()} ({round(self._needs.fullness)})\n"
            f"기분: {self._mood.label()} ({round(self._mood.value)})\n"
            f"함께한 시간: {format_active(r.active_s)}\n"
            f"먹은 횟수: {r.meals}"
        )

    # ------------------------------------------------------------------ 마우스 이벤트

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 이름 규칙)
        if not self._input_enabled:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = self._cursor()
            self._pointer.press(x, y, self._body.cx, self._body.feet_y)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.contextRequested.emit(self)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if not self._input_enabled:
            return
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

    # ------------------------------------------------------------------ 내부: 시간 진행

    def _on_timer(self) -> None:
        active, hidden = self._status()
        try:
            self.advance(time.perf_counter(), active=active, hidden=hidden)
        except Exception:  # 한 프레임의 오류로 프로그램이 죽지 않게 한다
            log.exception("펫 갱신 중 오류")

    def _step_body(self, sim_dt: float) -> None:
        world = self._poller.latest
        remaining = sim_dt
        while remaining > 1e-9:
            step = min(remaining, self._max_step)
            self._body.update(step, world)
            remaining -= step

    def _step_toy(self, paused: bool) -> None:
        # 공은 걷는 펫만 가지고 논다 (헤엄치는 펫은 무시한다)
        if self._toy is None or paused or self._feeding.target is not None:
            return
        if self._body.movement != "walker":
            return
        self._toy.tick_pet(self._body)

    def _update_pointer(self, now: float) -> None:
        x, y = self._cursor()
        result = self._pointer.poll(now, x, y)
        if result.hold is not None:
            self._body.hold(*result.hold)
        if result.petted and not self._needs.dead:
            joy_seconds = self._mood.petted()
            self._body.on_petted(joy_seconds)

    def _check_critical(self) -> None:
        critical = self._needs.is_critical()
        if critical and not self._critical_sent:
            self._critical_sent = True
            self.noticed.emit(f"{self.record.name}가 많이 배고파해요")
        elif not critical:
            self._critical_sent = False

    def _check_growth(self, now: float) -> None:
        if self._needs.dead:
            return
        target = stage_for(
            self.record.active_s,
            self.record.meals,
            hours=self._cfg.growth.hours,
            meal_counts=self._cfg.growth.meals,
            current=self.stage,
        )
        if target > self.stage:
            self.stage = target
            self.record.stage = target
            self._sprites = SpriteBank(self._spec, target)  # 새 단계 그림
            self._sprites.load()
            self._resize_body()
            self._grow_left = _GROW_S
            self._art_key = None
            self.noticed.emit(f"{self.record.name}가 {target}단계로 자랐어요!")
            log.info("펫 성장: %s %d단계", self.record.name, target)

    def _on_death(self, now: float) -> None:
        self._body.set_frozen(True)
        self._death_at = now
        self._feeding.release(self._body)
        self._critical_sent = True
        self.record.died_at = time.time()
        self.noticed.emit(f"{self.record.name}가 떠났어요")
        log.info("펫이 사망했습니다: %s", self.record.name)

    def _resize_body(self) -> None:
        factor = self._factor()
        frame_w, frame_h = self._spec.frame_size
        self._body.resize(
            frame_w * factor,
            self._spec.ground_y * factor,
            below=(frame_h - self._spec.ground_y) * factor,
        )

    def _factor(self) -> int:
        return physical_scale(pixel_scale_for(self.stage, self._cfg.growth.pixel_scale), self._dpr)

    def _write_back(self) -> None:
        r = self.record
        r.stage = self.stage
        r.fullness = round(self._needs.fullness, 3)
        r.hunger_s = round(self._needs.hunger_s, 3)
        r.mood = round(self._mood.value, 3)
        r.dead = self._needs.dead
        if self._buried:
            r.grave_cx = float(self._body.cx)
            r.grave_feet_y = float(self._body.feet_y)
        if self._needs.dead:
            tip = f"{r.name}\n{self.stage}단계 · 함께한 시간 {format_active(r.active_s)}"
            if tip != self._tip:
                self._tip = tip
                self.setToolTip(tip)

    # ------------------------------------------------------------------ 내부: 그림

    def _apply_position(self) -> None:
        x = round(self._body.window_left)
        y = round(self._body.window_top)
        if self._placed == (x, y):
            return
        move_window(int(self.winId()), x, y)
        self._placed = (x, y)

    def _display_action(self) -> str:
        """몸 상태(물리)가 고른 동작에 성장, 기분, 배고픔 그림을 덧씌운다."""
        actions = self._spec.actions
        if self._grow_left > 0 and "happy" in actions:
            return "happy"
        action = self._body.action()
        if action not in _OVERRIDE_ACTIONS:
            return action
        if self._mood.is_joyful and "happy" in actions:
            return "happy"
        if self._needs.is_critical() and "sick" in actions:
            return "sick"  # 위독: 누워 있는 그림
        if self._needs.is_hungry() and "hungry" in actions:
            return "hungry"
        if self._mood.is_sad and "sad" in actions:
            return "sad"
        return action

    def _sync_art(self, now: float) -> None:
        if self._needs.dead:
            if self._death_at is None:
                self._death_at = now
            if self._buried:
                self._show_art(_TOMB, 0, self._sprites.tomb())
                return
            die_spec = self._spec.actions[_DEATH]
            if now - self._death_at >= die_spec.frames / die_spec.fps and self._body.settled():
                self._buried = True
                self.buried.emit(self)
                self._show_art(_TOMB, 0, self._sprites.tomb())
                return
            action = _DEATH
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
        badge = self._needs.is_critical() and not self._needs.dead
        key = (name, index, facing, self.stage, badge)
        if key == self._art_key:
            return
        if facing < 0:
            # 기본 그림은 오른쪽을 보고 있다. 왼쪽은 좌우 반전한다.
            image = image.flipped(Qt.Orientation.Horizontal)
        if badge:
            image = _with_badge(image)
        self._art_key = key
        self.set_art(image, pixel_scale_for(self.stage, self._cfg.growth.pixel_scale))


def _with_badge(image: QImage) -> QImage:
    """위독 표시: 머리 위 오른쪽에 빨간 '!' 배지를 그린다."""
    out = image.copy()
    size = max(4, out.width() // 3)
    painter = QPainter(out)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(220, 40, 40))
    painter.drawEllipse(QRect(out.width() - size, 0, size, size))
    painter.setPen(QColor(255, 255, 255))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(max(3, size - 2))
    painter.setFont(font)
    painter.drawText(QRect(out.width() - size, 0, size, size), Qt.AlignmentFlag.AlignCenter, "!")
    painter.end()
    return out
