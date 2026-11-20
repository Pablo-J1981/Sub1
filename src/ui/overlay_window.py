"""테두리 없는 투명 최상위 창의 공통 기반 클래스.

펫, 먹이, 아이템, 무덤이 모두 이 창을 상속한다.
그림의 불투명 픽셀만 클릭을 받고, 나머지는 뒤쪽 창으로 통과한다.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from core.render_math import opaque_runs, physical_scale, scale_runs
from platform_win.click_region import set_click_region


class OverlayWindow(QWidget):
    """투명 오버레이 창. 작업 표시줄에 나타나지 않는다(Qt.Tool)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet("background: transparent;")

        self._label = QLabel(self)
        self._label.setStyleSheet("background: transparent;")
        self._label.move(0, 0)

    def set_art(self, image: QImage, base_scale: int) -> None:
        """그림을 정수 배율로 최근접 이웃 확대해 표시하고 클릭 영역을 갱신한다.

        base_scale: 논리 배율(config의 pet_scale). 실제 확대는 DPI 배율을 반영한다.
        """
        dpr = self.devicePixelRatioF()
        factor = physical_scale(base_scale, dpr)

        src_w, src_h = image.width(), image.height()
        big = image.scaled(
            src_w * factor,
            src_h * factor,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,  # 최근접 이웃: 도트가 흐려지지 않음
        )
        pixmap = QPixmap.fromImage(big)
        pixmap.setDevicePixelRatio(dpr)

        logical = QSize(round(big.width() / dpr), round(big.height() / dpr))
        self.setFixedSize(logical)
        self._label.setFixedSize(logical)
        self._label.setPixmap(pixmap)

        # 클릭 영역은 물리 픽셀 기준이다. 원본 알파를 구한 뒤 같은 배율로 확대한다.
        runs = scale_runs(opaque_runs(_alpha_rows(image)), factor)
        set_click_region(int(self.winId()), runs)  # winId() 호출 시 네이티브 창이 만들어진다


def _alpha_rows(image: QImage) -> list[list[int]]:
    """ARGB 이미지의 알파 값을 행 단위 리스트로 반환한다 (Qt 픽셀 접근 한 번으로 처리)."""
    argb = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = argb.width(), argb.height()
    stride = argb.bytesPerLine()
    buf = bytes(argb.constBits())
    rows: list[list[int]] = []
    for y in range(height):
        row_start = y * stride
        # ARGB32 리틀엔디언 메모리 순서는 B, G, R, A 이므로 알파는 4바이트마다 네 번째 값
        rows.append([buf[row_start + x * 4 + 3] for x in range(width)])
    return rows
