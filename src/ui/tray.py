"""트레이 아이콘과 메뉴.

고정 항목: 펫 숨기기/보이기, 종료. 그 사이에 동적 항목(펫별 메뉴 등)을 넣는다.
동적 항목은 메뉴를 열 때마다 set_before_show 로 등록한 함수가 다시 채운다.
알림은 풍선 알림으로 보낸다.
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
        self._sep = menu.addSeparator()
        quit_action = QAction("종료", menu)
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)
        self._menu = menu  # 참조를 유지해야 메뉴가 사라지지 않는다
        self._dynamic: list[QAction] = []
        self._keep: list[QMenu] = []  # 하위 메뉴 참조 유지

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

    def set_before_show(self, fill: Callable[["TrayController"], None]) -> None:
        """메뉴를 열기 직전마다 fill(self) 를 불러 동적 항목을 다시 채운다."""
        self._menu.aboutToShow.connect(lambda: (self.clear_dynamic(), fill(self)))

    def clear_dynamic(self) -> None:
        for action in self._dynamic:
            self._menu.removeAction(action)
        self._dynamic.clear()
        self._keep.clear()

    def add_item(self, text: str, callback: Callable[[], None], enabled: bool = True) -> None:
        action = QAction(text, self._menu)
        action.triggered.connect(lambda *_: callback())
        action.setEnabled(enabled)
        self._menu.insertAction(self._sep, action)
        self._dynamic.append(action)

    def add_menu(self, submenu: QMenu) -> None:
        self._keep.append(submenu)
        self._menu.insertMenu(self._sep, submenu)
        self._dynamic.append(submenu.menuAction())

    def notify(self, title: str, message: str) -> None:
        if self._tray.isVisible():
            self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # 트레이 아이콘 더블클릭 시 보이기/숨기기 토글
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_action.trigger()


def make_tray_icon(pixmap: QPixmap) -> QIcon:
    return QIcon(pixmap)
