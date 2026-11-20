"""트레이 아이콘과 메뉴.

1단계 메뉴: 펫 보이기/숨기기, 종료.
자동 실행 토글은 8단계에서 추가한다.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TrayController:
    def __init__(
        self,
        icon: QIcon,
        on_toggle_visible: Callable[[], None],
        on_quit: Callable[[], None],
        parent=None,
    ) -> None:
        self._tray = QSystemTrayIcon(icon, parent)
        self._tray.setToolTip("데스크톱 펫")

        menu = QMenu()
        self._toggle_action = QAction("펫 숨기기", menu)
        self._toggle_action.triggered.connect(on_toggle_visible)
        menu.addAction(self._toggle_action)
        menu.addSeparator()
        quit_action = QAction("종료", menu)
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)
        self._menu = menu  # 참조를 유지해야 메뉴가 사라지지 않는다

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    @staticmethod
    def is_available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_visible_state(self, visible: bool) -> None:
        self._toggle_action.setText("펫 숨기기" if visible else "펫 보이기")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # 트레이 아이콘 더블클릭 시 보이기/숨기기 토글
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_action.trigger()


def make_tray_icon(pixmap: QPixmap) -> QIcon:
    return QIcon(pixmap)
