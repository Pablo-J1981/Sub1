"""그림 파일이 없을 때 쓰는 임시 그림 (동작 이름이 적힌 색 네모).

나중에 assets 폴더에 PNG를 넣으면 로더가 이 그림 대신 실제 그림을 쓴다.
같은 이름은 항상 같은 색이 나오도록 이름의 해시로 색을 정한다.
"""

from __future__ import annotations

import zlib

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

TRANSPARENT = QColor(0, 0, 0, 0)


def color_for_label(label: str) -> QColor:
    hue = zlib.crc32(label.encode("utf-8")) % 360
    return QColor.fromHsv(hue, 150, 235)


def make_placeholder_image(
    label: str,
    size: tuple[int, int],
    fill: QColor | None = None,
) -> QImage:
    """size 크기의 투명 배경 위에 색 네모와 라벨을 그린 ARGB 이미지를 만든다."""
    width, height = size
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(TRANSPARENT)

    color = fill or color_for_label(label)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # 도트 느낌 유지
        painter.setPen(QPen(QColor(30, 30, 30), 1))
        painter.setBrush(color)
        painter.drawRect(QRect(0, 0, width - 1, height - 1))

        font = QFont()
        font.setPixelSize(max(6, min(width, height) // 5))
        painter.setFont(font)
        painter.setPen(QColor(20, 20, 20))
        painter.drawText(QRect(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, label)
    finally:
        painter.end()
    return image
