"""떨어지거나 놓여 있는 먹이를 화면에 그린다.

먹이 한 개가 창 한 개다 (ItemView). 먹이 목록(FoodPool)이 바뀌면 창을 맞춘다.
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtGui import QImage

from core.feeding import FoodItem
from ui.item_view import ItemView


class FoodLayer:
    def __init__(self, images: dict[str, QImage], base_scale: int) -> None:
        self._images = images
        self._scale = int(base_scale)
        self._views: dict[int, ItemView] = {}

    def sync(self, items: Sequence[FoodItem], allowed: bool) -> None:
        live = {item.id for item in items}
        for fid in [k for k in self._views if k not in live]:
            self._discard(self._views.pop(fid))
        for item in items:
            image = self._images.get(item.kind)
            if image is None or image.isNull():
                continue
            view = self._views.get(item.id)
            if view is None:
                view = ItemView(image, self._scale)
                view.set_passive()
                self._views[item.id] = view
            w, h = view.physical_size()
            view.set_allowed(allowed)
            view.show_at(item.x - w / 2, item.y - h)  # 발 기준선이 먹이 아랫변

    def set_allowed(self, allowed: bool) -> None:
        for view in self._views.values():
            view.set_allowed(allowed)

    def clear(self) -> None:
        for view in self._views.values():
            self._discard(view)
        self._views.clear()

    @staticmethod
    def _discard(view: ItemView) -> None:
        view.hide_item()
        view.close()
        view.deleteLater()
