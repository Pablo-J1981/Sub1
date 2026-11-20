"""애플리케이션 조립(부트스트랩). 설정, 로깅, DPI, Qt 앱, 임시 펫 창, 트레이를 연결한다."""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from core.config import ConfigError, load_config
from core.logging_setup import install_excepthook, setup_logging
from platform_win.dpi import enable_per_monitor_dpi_v2
from platform_win.paths import app_root, data_dir
from ui.overlay_window import OverlayWindow
from ui.placeholder import make_placeholder_image
from ui.tray import TrayController, make_tray_icon


class PlaceholderPetWindow(OverlayWindow):
    """1단계 임시 펫. 실제 펫 로직이 들어올 때까지 색 원 하나를 보여 준다."""

    def __init__(self, base_scale: int, frame_size: tuple[int, int]) -> None:
        super().__init__()
        self._base_scale = base_scale
        image = make_placeholder_image("idle", frame_size, QColor(230, 150, 60))
        self.set_art(image, base_scale)


class DesktopPetApp:
    def __init__(self, qt_app: QApplication, logger: logging.Logger) -> None:
        self._qt_app = qt_app
        self._log = logger
        self._pet_window: PlaceholderPetWindow | None = None
        self._tray: TrayController | None = None

    def start(self, base_scale: int, frame_size: tuple[int, int]) -> None:
        self._pet_window = PlaceholderPetWindow(base_scale, frame_size)
        self._pet_window.show()

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
        self._log.info("임시 펫 창을 시작했습니다.")

    def toggle_visible(self) -> None:
        if self._pet_window is None or self._tray is None:
            return
        visible = not self._pet_window.isVisible()
        self._pet_window.setVisible(visible)
        self._tray.set_visible_state(visible)

    def quit(self) -> None:
        self._log.info("종료합니다.")
        self._qt_app.quit()


def run() -> int:
    root = app_root()
    log_dir = data_dir()
    logger = setup_logging(log_dir / "app.log")
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

    app = DesktopPetApp(qt_app, logger)
    app.start(
        base_scale=config.display.pet_scale,
        frame_size=config.debug.placeholder_frame_size,
    )
    return qt_app.exec()
