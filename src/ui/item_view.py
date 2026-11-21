"""먹이 그릇, 무덤처럼 펫 옆에 놓여 있는 그림 창.

펫 창과 같은 방식으로 정수 배율 확대, 클릭 통과, 작업 표시줄 숨김을 쓴다.
위치는 물리 픽셀 좌표로 SetWindowPos를 통해 옮긴다 (바뀔 때만 옮긴다).
펫 창이 숨겨지면 이 창도 함께 숨기도록 set_allowed()로 알려 준다.
"""

from __future__ import annotations

from PySide6.QtGui import QImage

from core.render_math import physical_scale
from platform_win.click_region import set_click_region
from platform_win.windows import move_window
from ui.overlay_window import OverlayWindow


class ItemView(OverlayWindow):
    def __init__(self, image: QImage, base_scale: int) -> None:
        super().__init__()
        self._image = image
        self._base_scale = base_scale
        self._wanted = False          # 보여 달라고 요청했는지
        self._allowed = True          # 펫 창이 보이는 상태인지
        self._target: tuple[int, int] | None = None
        self._placed: tuple[int, int] | None = None
        self.set_art(image, base_scale)
        self.hide()

    @property
    def wanted(self) -> bool:
        return self._wanted

    def physical_size(self) -> tuple[int, int]:
        factor = physical_scale(self._base_scale, self.devicePixelRatioF())
        return self._image.width() * factor, self._image.height() * factor

    def show_at(self, left: float, top: float) -> None:
        """물리 픽셀 기준 왼쪽 위 좌표에 보이게 한다."""
        self._wanted = True
        self._target = (round(left), round(top))
        self._refresh()

    def hide_item(self) -> None:
        self._wanted = False
        self._refresh()

    def set_passive(self) -> None:
        """클릭을 모두 뒤쪽 창으로 넘긴다 (먹이, 공처럼 누를 필요가 없는 물건)."""
        set_click_region(int(self.winId()), [])

    def set_allowed(self, allowed: bool) -> None:
        self._allowed = bool(allowed)
        self._refresh()

    def _refresh(self) -> None:
        show = self._wanted and self._allowed and self._target is not None
        if not show:
            if self.isVisible():
                self.hide()
            return
        if self._placed != self._target:
            move_window(int(self.winId()), *self._target)
            self._placed = self._target
        if not self.isVisible():
            self.show()
