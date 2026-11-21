"""무덤 창. 죽은 펫이 있던 자리에 놓인다. 물리는 없고, 사용자가 끌어서 옮길 수 있다.

- 마우스를 올리면 이름, 단계, 함께한 시간이 보인다 (툴팁).
- 왼쪽 드래그로 옮기면 놓은 자리가 기록된다 (moved 신호).
- 오른쪽 클릭은 메뉴를 연다 (contextRequested 신호).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage

from core.render_math import physical_scale
from core.records import PetRecord
from platform_win.windows import get_cursor_pos
from ui.item_view import ItemView


class GraveView(ItemView):
    contextRequested = Signal(object)  # 오른쪽 클릭 (GraveView 자신)
    moved = Signal(object)             # 끌어서 옮긴 뒤 (GraveView 자신)

    def __init__(self, image: QImage, base_scale: int, ground_y: int, record: PetRecord) -> None:
        super().__init__(image, base_scale)
        self.record = record
        self._ground_y = int(ground_y)   # 원본 픽셀: 그림 안에서 발이 닿는 y (무덤 바닥선)
        self._left = 0
        self._top = 0
        self._drag: tuple[int, int, int, int] | None = None
        self._input = True

    # ------------------------------------------------------------------ 위치

    def ground_px(self) -> int:
        return round(self._ground_y * physical_scale(self._base_scale, self.devicePixelRatioF()))

    def place(self, cx: float, feet_y: float) -> None:
        w, _ = self.physical_size()
        self.show_at(cx - w / 2, feet_y - self.ground_px())

    def center_x(self) -> float:
        w, _ = self.physical_size()
        return self._left + w / 2

    def feet_y(self) -> float:
        return self._top + self.ground_px()

    def show_at(self, left: float, top: float) -> None:
        self._left, self._top = round(left), round(top)
        super().show_at(left, top)

    def set_info(self, text: str) -> None:
        self.setToolTip(text)

    def set_input_enabled(self, enabled: bool) -> None:
        self._input = bool(enabled)

    # ------------------------------------------------------------------ 마우스

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._input:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = get_cursor_pos()
            self._drag = (x, y, self._left, self._top)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.contextRequested.emit(self)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            super().mouseMoveEvent(event)
            return
        x, y = get_cursor_pos()
        sx, sy, left, top = self._drag
        self.show_at(left + x - sx, top + y - sy)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag is not None:
            self._drag = None
            self.moved.emit(self)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
