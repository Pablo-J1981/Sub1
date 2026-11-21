"""애플리케이션 조립(부트스트랩). 설정, 로깅, DPI, 펫, 트레이를 연결한다."""

from __future__ import annotations

import logging
import random
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from core.config import AppConfig, ConfigError, load_config
from core.geometry import spawn_point
from core.logging_setup import install_excepthook, setup_logging
from core.mood import Mood
from core.needs import Needs
from core.pet_spec import load_pet_spec
from core.pointer import PetPointer
from core.render_math import physical_scale
from pets import create_pet
from platform_win.dpi import enable_per_monitor_dpi_v2
from platform_win.paths import app_root, data_dir
from ui.pet_view import PetView
from ui.placeholder import make_placeholder_image
from ui.sprites import SpriteBank
from ui.tray import TrayController, make_tray_icon
from ui.world_poller import WorldPoller


class DesktopPetApp:
    def __init__(
        self,
        qt_app: QApplication,
        logger: logging.Logger,
        root: Path,
        config: AppConfig,
    ) -> None:
        self._qt_app = qt_app
        self._log = logger
        self._root = root
        self._config = config
        self._poller: WorldPoller | None = None
        self._pet: PetView | None = None
        self._tray: TrayController | None = None

    def start(self) -> None:
        cfg = self._config
        dpr = self._qt_app.primaryScreen().devicePixelRatio()
        factor = physical_scale(cfg.display.pet_scale, dpr)  # 물리 픽셀 / 원본 픽셀

        self._poller = WorldPoller(cfg.physics.window_poll_hz, cfg.physics.min_surface_width)
        self._poller.refresh()

        spec = load_pet_spec(self._root / "assets" / "pets" / cfg.debug.start_pet)
        if spec.movement != "walker":
            raise ValueError(f"아직 지원하지 않는 이동 타입입니다: {spec.movement}")
        sprites = SpriteBank(spec)
        sprites.load()
        if sprites.missing:
            self._log.warning(
                "그림이 없어 임시 그림을 씁니다: %s (%s)", spec.key, ", ".join(sprites.missing)
            )

        frame_w, _ = spec.frame_size
        body = create_pet(
            spec.movement,
            width=frame_w * factor,
            ground_offset=spec.ground_y * factor,
            unit=factor,
            physics=cfg.physics,
            behavior=cfg.walker,
            rng=random.Random(),
        )
        pointer_cfg = cfg.pointer
        pointer = PetPointer(
            drag_threshold=pointer_cfg.drag_threshold_px * factor,
            min_stroke=pointer_cfg.min_stroke_px * factor,
            throw_inertia=pointer_cfg.throw_inertia,
            max_throw_speed=pointer_cfg.max_throw_speed * factor,
            velocity_window_s=pointer_cfg.velocity_window_s,
        )
        food_path = self._root / "assets" / "items" / "food_bowl.png"
        food_image = QImage(str(food_path))
        if food_image.isNull():
            self._log.warning("먹이 그림이 없어 먹이 기능을 끕니다: %s", food_path)
        self._pet = PetView(
            body, spec, sprites, self._poller,
            cfg.display.pet_scale, cfg.display.animation_fps,
            mood=Mood(cfg.mood),
            pointer=pointer,
            needs=Needs(cfg.needs),
            food_image=None if food_image.isNull() else food_image,
            time_scale=cfg.debug.time_scale,
            max_step_s=cfg.physics.max_step_s,
        )
        self._pet.hideRequested.connect(self.toggle_visible)
        self._pet.quitRequested.connect(self.quit)
        self._pet.restartRequested.connect(self.restart_pet)
        cx, feet_y = self._spawn_point(factor)
        self._pet.spawn(cx, feet_y)
        self._pet.show()

        self._poller.start()
        self._pet.start()
        self._start_tray()
        self._log.info("펫을 시작했습니다: %s (배율 %d)", spec.key, factor)

    def restart_pet(self) -> None:
        """사망 후 다시 시작: 처음 위치 위에서 다시 떨어뜨린다."""
        if self._pet is None:
            return
        factor = physical_scale(self._config.display.pet_scale, self._qt_app.primaryScreen().devicePixelRatio())
        cx, feet_y = self._spawn_point(factor)
        self._pet.restart(cx, feet_y)
        self._log.info("펫을 다시 시작했습니다.")

    def _spawn_point(self, factor: float) -> tuple[float, float]:
        """첫 실행 위치: 첫 모니터 작업 영역 가운데 위에서 떨어뜨린다."""
        assert self._poller is not None
        monitors = self._poller.latest.monitors
        if not monitors:
            self._log.warning("모니터 정보를 읽지 못해 펫이 움직이지 않습니다.")
            return 0.0, 0.0
        return spawn_point(monitors[0].work, self._config.physics.spawn_height, factor)

    def _start_tray(self) -> None:
        icon_pixmap = QPixmap.fromImage(
            make_placeholder_image("P", (32, 32), QColor(120, 180, 255))
        )
        self._tray = TrayController(
            make_tray_icon(icon_pixmap),
            on_toggle_visible=self.toggle_visible,
            on_quit=self.quit,
        )
        if TrayController.is_available():
            self._tray.show()
        else:
            self._log.warning("시스템 트레이를 사용할 수 없습니다.")

    def toggle_visible(self) -> None:
        if self._pet is None or self._tray is None:
            return
        visible = not self._pet.isVisible()
        self._pet.setVisible(visible)
        self._tray.set_visible_state(visible)

    def quit(self) -> None:
        self._log.info("종료합니다.")
        if self._pet is not None:
            self._pet.stop()
        if self._poller is not None:
            self._poller.stop()
        self._qt_app.quit()


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
        QMessageBox.critical(None, "데스크톱 펫", f"설정 파일 오류:\n{exc}")
        return 1

    app = DesktopPetApp(qt_app, logger, root, config)
    try:
        app.start()
    except (ValueError, OSError) as exc:  # PetSpecError 는 ValueError 하위 클래스
        logger.error("시작 실패: %s", exc)
        QMessageBox.critical(None, "데스크톱 펫", f"펫을 시작하지 못했습니다:\n{exc}")
        return 1
    return qt_app.exec()
