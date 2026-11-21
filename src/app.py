"""애플리케이션 조립: 저장, 펫 목록, 먹이와 공, 무덤, 트레이 메뉴를 연결한다."""

from __future__ import annotations

import logging
import random
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
)

from core.clock import is_active
from core.config import AppConfig, ConfigError, load_config
from core.feeding import FoodPool
from core.geometry import spawn_point
from core.growth import pixel_scale_for
from core.items import ItemPack, LocalAlwaysAllow, entitled, load_item_packs
from core.logging_setup import install_excepthook, setup_logging
from core.pet_spec import PetSpec, load_pet_spec
from core.pointer import PetPointer
from core.records import (
    MAX_NAME_LEN,
    PetRecord,
    can_adopt,
    grave_tip,
    living,
    memory_text,
    next_id,
)
from core.render_math import physical_scale
from core.savefile import SaveData, load_save, save_data
from core.toy import BallToy
from pets import create_pet
from platform_win.dpi import enable_per_monitor_dpi_v2
from platform_win.paths import app_root, data_dir
from platform_win.windows import VK_ESCAPE, VK_LBUTTON, VK_RBUTTON, get_cursor_pos, idle_seconds, key_down
from ui.adopt_dialog import AdoptDialog, PetChoice
from ui.food_layer import FoodLayer
from ui.grave_view import GraveView
from ui.item_view import ItemView
from ui.pet_view import PetView
from ui.placeholder import make_placeholder_image
from ui.sprites import SpriteBank
from ui.tray import TrayController, make_tray_icon
from ui.world_poller import WorldPoller

SAVE_NAME = "save.json"
APP_TITLE = "데스크톱 펫"


class DesktopPetApp:
    def __init__(self, qt_app: QApplication, logger: logging.Logger, root: Path, config: AppConfig) -> None:
        self._qt_app = qt_app
        self._log = logger
        self._root = root
        self._cfg = config
        self._save_path = data_dir() / SAVE_NAME

        self._dpr = 1.0
        self._unit = 1.0
        self._poller: WorldPoller | None = None
        self._specs: dict[str, PetSpec] = {}
        self._food_packs: list[ItemPack] = []
        self._toy_packs: list[ItemPack] = []
        self._pool: FoodPool | None = None
        self._toy: BallToy | None = None
        self._food_layer: FoodLayer | None = None
        self._ball_view: ItemView | None = None
        self._records: list[PetRecord] = []
        self._views: dict[int, PetView] = {}     # 살아 있는 펫 (죽어서 가라앉는 중 포함)
        self._graves: dict[int, GraveView] = {}  # 무덤
        self._tray: TrayController | None = None
        self._pets_visible = True
        self._placing: ItemPack | None = None
        self._ghost: ItemView | None = None
        self._prev_left = False
        self._prev_cancel = False
        self._frame_timer: QTimer | None = None
        self._autosave: QTimer | None = None
        self._last_frame: float | None = None
        self._closing = False

    # ------------------------------------------------------------------ 시작과 종료

    def start(self) -> bool:
        """False면 시작하지 않았다 (첫 실행에서 펫을 고르지 않고 취소한 경우)."""
        cfg = self._cfg
        self._dpr = self._qt_app.primaryScreen().devicePixelRatio()
        self._unit = physical_scale(cfg.display.pet_scale, self._dpr)

        self._poller = WorldPoller(cfg.physics.window_poll_hz, cfg.physics.min_surface_width)
        self._poller.refresh()

        self._specs = self._discover_pets()
        if not self._specs:
            raise ValueError("assets/pets 에 쓸 수 있는 동물이 없습니다.")

        packs, errors = load_item_packs(self._root / "assets" / "items")
        for err in errors:
            self._log.warning("아이템 건너뜀: %s", err)
        provider = LocalAlwaysAllow()
        self._food_packs = entitled(packs, provider, "food")
        self._toy_packs = entitled(packs, provider, "toy")

        u = self._unit
        self._pool = FoodPool(
            lifetime_s=cfg.food.lifetime_s,
            max_items=cfg.food.max_items,
            gravity=cfg.physics.gravity * u,
            max_fall=cfg.physics.max_fall_speed * u,
            sink_speed=cfg.swimmer.sink_speed * u,
        )
        self._toy = BallToy(cfg.toy, u)
        images = {p.id: QImage(str(p.image)) for p in self._food_packs + self._toy_packs}
        self._food_layer = FoodLayer(images, cfg.display.pet_scale)
        self._images = images

        self._load()
        if not living(self._records) and not self._adopt_dialog() and not self._records:
            return False  # 첫 실행에서 펫을 고르지 않고 닫았다

        for record in self._records:
            if record.dead:
                self._add_grave(record)
            else:
                self._add_pet(record)

        self._start_tray()
        self._frame_timer = QTimer(self._qt_app)
        self._frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame_timer.setInterval(max(1, round(1000 / cfg.display.animation_fps)))
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start()

        self._autosave = QTimer(self._qt_app)
        self._autosave.setInterval(max(1, round(cfg.activity.autosave_s * 1000)))
        self._autosave.timeout.connect(self._save)
        self._autosave.start()

        self._poller.start()
        for view in self._views.values():
            view.start()
        self._log.info("펫 %d마리를 시작했습니다.", len(self._views))
        return True

    def quit(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._log.info("종료합니다.")
        self._cancel_placement()
        for timer in (self._frame_timer, self._autosave):
            if timer is not None:
                timer.stop()
        for view in self._views.values():
            view.stop()
        if self._poller is not None:
            self._poller.stop()
        self._save()
        if self._tray is not None:
            self._tray.hide()
        self._qt_app.quit()

    # ------------------------------------------------------------------ 저장

    def _load(self) -> None:
        data, warnings = load_save(self._save_path)
        for warning in warnings:
            self._log.warning(warning)
        if data is None and warnings:
            self._log.warning("저장 파일을 읽지 못해 새로 시작합니다.")
        self._records = list(data.records) if data is not None else []

    def _save(self) -> None:
        try:
            save_data(self._save_path, SaveData(records=list(self._records),
                                                next_id=next_id(self._records)))
        except OSError as exc:
            self._log.error("저장하지 못했습니다: %s", exc)
            self._notify(f"저장하지 못했어요: {exc}")

    # ------------------------------------------------------------------ 펫 목록

    def _discover_pets(self) -> dict[str, PetSpec]:
        specs: dict[str, PetSpec] = {}
        base = self._root / "assets" / "pets"
        if not base.is_dir():
            return specs
        for folder in sorted(p for p in base.iterdir() if (p / "pet.json").is_file()):
            try:
                specs[folder.name] = load_pet_spec(folder)
            except (ValueError, OSError) as exc:
                self._log.warning("동물을 건너뜀: %s (%s)", folder.name, exc)
        return specs

    def _new_record(self, animal: str, name: str) -> PetRecord:
        cfg = self._cfg
        return PetRecord(
            id=next_id(self._records),
            animal=animal,
            name=name,
            fullness=cfg.needs.start,
            mood=cfg.mood.start,
        )

    def _live_views(self) -> list[PetView]:
        return [v for v in self._views.values() if not v.record.dead]

    def _spawn_xy(self, offset_index: int) -> tuple[float, float]:
        assert self._poller is not None
        monitors = self._poller.latest.monitors
        if not monitors:
            self._log.warning("모니터 정보를 읽지 못해 펫이 움직이지 않습니다.")
            return 0.0, 0.0
        cx, feet = spawn_point(monitors[0].work, self._cfg.physics.spawn_height, self._unit)
        cx += offset_index * 60 * self._unit
        work = monitors[0].work
        cx = min(max(cx, work.left + 30 * self._unit), work.right - 30 * self._unit)
        return cx, feet

    def _add_pet(self, record: PetRecord) -> PetView:
        spec = self._specs[record.animal]
        cfg = self._cfg
        stage = record.stage
        factor = physical_scale(pixel_scale_for(stage, cfg.growth.pixel_scale), self._dpr)
        fw, fh = spec.frame_size
        sprites = SpriteBank(spec, stage)
        sprites.load()
        if sprites.missing:
            self._log.warning("그림이 없어 임시 그림을 씁니다: %s (%s)", spec.key, ", ".join(sprites.missing))
        body = create_pet(
            spec.movement,
            width=fw * factor,
            ground_offset=spec.ground_y * factor,
            unit=self._unit,
            physics=cfg.physics,
            behavior=cfg.walker,
            swimmer=cfg.swimmer,
            rng=random.Random(),
            below=(fh - spec.ground_y) * factor,
        )
        u = self._unit
        pointer = PetPointer(
            drag_threshold=cfg.pointer.drag_threshold_px * u,
            min_stroke=cfg.pointer.min_stroke_px * u,
            throw_inertia=cfg.pointer.throw_inertia,
            max_throw_speed=cfg.pointer.max_throw_speed * u,
            velocity_window_s=cfg.pointer.velocity_window_s,
        )
        view = PetView(
            record, body, spec, sprites, self._poller, cfg, pointer,
            self._pool, self._toy, dpr=self._dpr, status=self._status,
        )
        view.noticed.connect(self._notify)
        view.buried.connect(self._on_buried)
        view.contextRequested.connect(self._on_pet_menu)
        cx, feet = self._spawn_xy(len(self._live_views()))
        view.spawn(cx, feet)
        view.setVisible(self._pets_visible)
        view.show()
        self._views[record.id] = view
        return view

    def _add_grave(self, record: PetRecord) -> GraveView | None:
        spec = self._specs.get(record.animal)
        if spec is None:
            self._log.warning("무덤을 그릴 동물이 없습니다: %s", record.animal)
            return None
        sprites = SpriteBank(spec, record.stage)
        sprites.load()
        scale = pixel_scale_for(record.stage, self._cfg.growth.pixel_scale)
        grave = GraveView(sprites.tomb(), scale, spec.ground_y, record)
        if record.grave_cx is not None and record.grave_feet_y is not None:
            grave.place(record.grave_cx, record.grave_feet_y)
        else:
            cx, feet = self._spawn_xy(0)
            grave.place(cx, feet)
        grave.set_info(grave_tip(record))
        grave.set_allowed(self._pets_visible)
        grave.contextRequested.connect(self._on_grave_menu)
        grave.moved.connect(self._on_grave_moved)
        self._graves[record.id] = grave
        return grave

    def _on_buried(self, view: PetView) -> None:
        """죽어서 가라앉은 펫을 무덤으로 바꾼다."""
        record = view.record
        record.grave_cx = float(view.body.cx)
        record.grave_feet_y = float(view.body.feet_y)
        view.stop()
        view.hide()
        view.deleteLater()
        self._views.pop(record.id, None)
        self._add_grave(record)
        self._log.info("무덤이 생겼습니다: %s", record.name)
        self._save()

    def _on_grave_moved(self, grave: GraveView) -> None:
        grave.record.grave_cx = float(grave.center_x())
        grave.record.grave_feet_y = float(grave.feet_y())
        self._save()

    # ------------------------------------------------------------------ 상태와 프레임

    def _status(self) -> tuple[bool, bool]:
        """(활성 사용 중인지, 펫이 숨겨졌는지). 활성은 마지막 입력이 idle_pause_s 안일 때."""
        active = is_active(idle_seconds(), self._cfg.activity.idle_pause_s)
        return active, not self._pets_visible

    def _on_frame(self) -> None:
        now = time.perf_counter()
        dt = 0.0 if self._last_frame is None else min(now - self._last_frame, 0.25)
        self._last_frame = now
        try:
            assert self._pool is not None and self._toy is not None and self._food_layer is not None
            self._pool.step(dt)
            self._toy.step(dt)
            self._food_layer.sync(self._pool.items, allowed=self._pets_visible)
            self._sync_ball()
            if self._placing is not None:
                self._update_placement()
        except Exception:  # 한 프레임의 오류로 프로그램이 죽지 않게 한다
            self._log.exception("먹이/공 갱신 중 오류")

    def _sync_ball(self) -> None:
        if self._toy is None or self._ball_view is None:
            return
        ball = self._toy.ball
        if ball is None:
            self._ball_view.hide_item()
            return
        w, h = self._ball_view.physical_size()
        self._ball_view.show_at(ball.x - w / 2, ball.y - h)
        self._ball_view.set_allowed(self._pets_visible)

    def toggle_visible(self) -> None:
        self._pets_visible = not self._pets_visible
        for view in self._views.values():
            view.setVisible(self._pets_visible)
        for grave in self._graves.values():
            grave.set_allowed(self._pets_visible)
        if not self._pets_visible:
            self._cancel_placement()
        if self._tray is not None:
            self._tray.set_visible_state(self._pets_visible)

    # ------------------------------------------------------------------ 먹이와 공 놓기

    def _start_placement(self, pack: ItemPack) -> None:
        if not self._live_views():
            self._notify("지금 먹일 펫이 없어요")
            return
        if not self._pets_visible:
            self.toggle_visible()
        self._cancel_placement()
        image = self._images.get(pack.id)
        if image is None or image.isNull():
            self._notify(f"그림을 읽지 못했어요: {pack.name_ko}")
            return
        self._placing = pack
        self._ghost = ItemView(image, self._cfg.display.pet_scale)
        self._ghost.set_passive()
        self._ghost.show_at(0, 0)
        self._prev_left = key_down(VK_LBUTTON)
        self._prev_cancel = key_down(VK_ESCAPE) or key_down(VK_RBUTTON)
        self._set_inputs(False)
        self._update_placement()

    def _update_placement(self) -> None:
        if self._ghost is None or self._placing is None:
            return
        x, y = get_cursor_pos()
        gw, gh = self._ghost.physical_size()
        self._ghost.show_at(x - gw / 2, y - gh / 2)
        cancel = key_down(VK_ESCAPE) or key_down(VK_RBUTTON)
        if cancel and not self._prev_cancel:
            self._cancel_placement()
            return
        self._prev_cancel = cancel
        left = key_down(VK_LBUTTON)
        if left and not self._prev_left:
            self._drop_at(x, y + gh / 2)  # 커서 아래쪽 가장자리를 먹이가 떨어지는 기준선으로 쓴다
        self._prev_left = left

    def _drop_at(self, x: float, feet_y: float) -> None:
        pack = self._placing
        if pack is None or self._pool is None or self._toy is None:
            return
        target = self._ground_under(x, feet_y)
        if target is None:
            return
        surface_y, left, right = target
        if pack.kind == "food":
            if feet_y > surface_y:
                feet_y = surface_y  # 발판 아래를 찍었으면 발판 위에 놓는다
            item = self._pool.drop(pack.id, x, feet_y, surface_y, sinking=pack.sinks)
            if item is None:
                self._notify("먹이가 너무 많아요. 펫이 먹은 뒤에 다시 놓아 주세요.")
            return
        if pack.kind == "toy":
            self._ball_view = self._make_item_view(pack)
            w, _ = self._ball_view.physical_size()
            self._toy.drop(x, surface_y, left, right, w / 2)
            self._cancel_placement()

    def _make_item_view(self, pack: ItemPack) -> ItemView:
        if self._ball_view is not None:
            self._ball_view.hide_item()
            self._ball_view.close()
            self._ball_view.deleteLater()
        view = ItemView(self._images[pack.id], self._cfg.display.pet_scale)
        view.set_passive()
        view.set_allowed(self._pets_visible)
        return view

    def _ground_under(self, x: float, y: float) -> tuple[float, float, float] | None:
        """(발판 높이, 발판 왼쪽, 발판 오른쪽). 창 발판이 없으면 작업 영역 바닥."""
        assert self._poller is not None
        world = self._poller.latest
        best = None
        for s in world.surfaces:
            if s.left <= x <= s.right and s.y >= y - 1e-6 and (best is None or s.y < best.y):
                best = s
        if best is not None:
            return float(best.y), float(best.left), float(best.right)
        for mon in world.monitors:
            if mon.work.left <= x < mon.work.right:
                return float(mon.work.bottom), float(mon.work.left), float(mon.work.right)
        return None

    def _cancel_placement(self) -> None:
        if self._ghost is not None:
            self._ghost.hide_item()
            self._ghost.close()
            self._ghost.deleteLater()
        self._ghost = None
        if self._placing is not None:
            self._placing = None
            self._set_inputs(True)

    def _set_inputs(self, enabled: bool) -> None:
        for view in self._views.values():
            view.set_input_enabled(enabled)
        for grave in self._graves.values():
            grave.set_input_enabled(enabled)

    def _start_toy(self) -> None:
        if not self._toy_packs:
            self._notify("공 그림이 없어요")
            return
        self._start_placement(self._toy_packs[0])

    # ------------------------------------------------------------------ 메뉴와 대화상자

    def _food_menu(self) -> QMenu:
        menu = QMenu("먹이 주기")
        for pack in self._food_packs:
            menu.addAction(pack.name_ko, lambda p=pack: self._start_placement(p))
        if not self._food_packs:
            menu.addAction("먹이 없음").setEnabled(False)
        return menu

    def _on_pet_menu(self, view: PetView) -> None:
        menu = QMenu()
        food = self._food_menu()  # 지역 변수로 잡아 두어야 메뉴가 닫히기 전에 사라지지 않는다
        menu.addAction("상태 보기", lambda *_: self._show_info(view))
        menu.addAction("이름 바꾸기", lambda *_: self._rename(view.record))
        menu.addMenu(food)
        menu.addAction("공 놓기", self._start_toy)
        menu.exec(QCursor.pos())

    def _on_grave_menu(self, grave: GraveView) -> None:
        record = grave.record
        menu = QMenu()
        menu.addAction("추억 보기", lambda *_: QMessageBox.information(None, record.name, memory_text(record)))
        menu.addAction("무덤 치우기", lambda *_: self._clear_grave(grave))
        menu.addSeparator()
        adopt = menu.addAction("새 펫 입양", lambda *_: self._adopt())
        adopt.setEnabled(can_adopt(self._records))
        menu.exec(QCursor.pos())

    def _show_info(self, view: PetView) -> None:
        QMessageBox.information(None, f"{view.record.name} 상태", view.info_text())

    def _rename(self, record: PetRecord) -> None:
        text, ok = QInputDialog.getText(
            None, "이름 바꾸기", f"새 이름 (최대 {MAX_NAME_LEN}자)",
            QLineEdit.EchoMode.Normal, record.name,
        )
        name = text.strip()[:MAX_NAME_LEN]
        if not ok or not name:
            return
        record.name = name
        grave = self._graves.get(record.id)
        if grave is not None:
            grave.set_info(grave_tip(record))
        self._save()

    def _clear_grave(self, grave: GraveView) -> None:
        record = grave.record
        answer = QMessageBox.question(
            None, "무덤 치우기",
            f"{record.name}의 무덤을 치울까요?\n치우면 기록이 지워지고 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._records = [r for r in self._records if r is not record]
        self._graves.pop(record.id, None)
        grave.hide_item()
        grave.close()
        grave.deleteLater()
        self._save()
        self._log.info("무덤을 치웠습니다: %s", record.name)

    def _choices(self) -> list[PetChoice]:
        scale = pixel_scale_for(1, self._cfg.growth.pixel_scale)
        choices: list[PetChoice] = []
        order = sorted(self._specs, key=lambda k: (k != self._cfg.debug.start_pet, k))
        for key in order:
            spec = self._specs[key]
            sprites = SpriteBank(spec, 1)
            sprites.load()
            img = sprites.frame("idle", 0)
            big = img.scaled(
                img.width() * scale, img.height() * scale,
                Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation,
            )
            choices.append(PetChoice(key, spec.name_ko, big))
        return choices

    def _adopt_dialog(self) -> bool:
        """동물과 이름을 고르고 새 펫을 만든다. 취소하면 False."""
        if not self._specs:
            return False
        dialog = AdoptDialog(self._choices(), self._cfg.debug.start_pet)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        record = self._new_record(dialog.animal, dialog.name)
        self._records.append(record)
        self._save()
        self._log.info("새 펫을 맞이했습니다: %s (%s)", record.name, record.animal)
        return True

    def _adopt(self) -> None:
        if not can_adopt(self._records):
            self._notify("5단계 펫이 있을 때 새 펫을 맞을 수 있어요")
            return
        if self._adopt_dialog():
            record = self._records[-1]
            self._add_pet(record).start()

    # ------------------------------------------------------------------ 트레이

    def _start_tray(self) -> None:
        icon_pixmap = QPixmap.fromImage(make_placeholder_image("P", (32, 32), QColor(120, 180, 255)))
        self._tray = TrayController(
            make_tray_icon(icon_pixmap),
            on_toggle_visible=self.toggle_visible,
            on_quit=self.quit,
        )
        self._tray.set_visible_state(self._pets_visible)
        self._tray.set_before_show(self._fill_tray)
        if TrayController.is_available():
            self._tray.show()
        else:
            self._log.warning("시스템 트레이를 사용할 수 없습니다.")

    def _fill_tray(self, tray: TrayController) -> None:
        has_live = bool(self._live_views())
        food = self._food_menu()
        food.setEnabled(has_live)
        tray.add_menu(food)
        tray.add_item("공 놓기", self._start_toy, enabled=has_live and bool(self._toy_packs))
        for view in self._live_views():
            sub = QMenu(f"{view.record.name} ({view.stage}단계)")
            sub.addAction("상태 보기", lambda *_, v=view: self._show_info(v))
            sub.addAction("이름 바꾸기", lambda *_, r=view.record: self._rename(r))
            tray.add_menu(sub)
        for grave in self._graves.values():
            sub = QMenu(f"{grave.record.name} 무덤")
            sub.addAction("추억 보기", lambda *_, r=grave.record: QMessageBox.information(
                None, r.name, memory_text(r)))
            sub.addAction("무덤 치우기", lambda *_, g=grave: self._clear_grave(g))
            tray.add_menu(sub)
        adoptable = can_adopt(self._records)
        label = "새 펫 입양" if adoptable else "새 펫 입양 (5단계 펫이 있거나 살아 있는 펫이 없을 때)"
        tray.add_item(label, self._adopt, enabled=adoptable)

    def _notify(self, text: str) -> None:
        self._log.info(text)
        if self._tray is not None:
            self._tray.notify(APP_TITLE, text)


def run() -> int:
    root = app_root()
    logger = setup_logging(data_dir() / "app.log")
    install_excepthook(logger)

    enable_per_monitor_dpi_v2()
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)  # 펫 창을 숨겨도 프로그램은 계속 실행
    qt_app.setApplicationName("DesktopPet")

    try:
        config = load_config(root / "config" / "settings.json")
    except ConfigError as exc:
        logger.error("설정 오류: %s", exc)
        QMessageBox.critical(None, APP_TITLE, f"설정 파일 오류:\n{exc}")
        return 1

    app = DesktopPetApp(qt_app, logger, root, config)
    try:
        started = app.start()
    except (ValueError, OSError) as exc:  # PetSpecError 는 ValueError 하위 클래스
        logger.error("시작 실패: %s", exc)
        QMessageBox.critical(None, APP_TITLE, f"펫을 시작하지 못했습니다:\n{exc}")
        return 1
    if not started:
        return 0
    return qt_app.exec()
