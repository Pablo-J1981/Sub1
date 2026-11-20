"""그림 파일이 없을 때 쓰는 임시 그림 (색 원 + 동작 이름).

나중에 assets 폴더에 PNG를 넣으면 로더가 이 그림 대신 실제 그림을 쓴다.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

TRANSPARENT = QColor(0, 0, 0, 0)


def make_placeholder_image(
    label: str,
    size: tuple[int, int],
    fill: QColor | None = None,
) -> QImage:
    """size 크기의 투명 배경 위에 원과 라벨을 그린 ARGB 이미지를 만든다."""
    width, height = size
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(TRANSPARENT)

    color = fill or QColor(230, 150, 60)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # 도트 느낌 유지
        painter.setPen(QPen(QColor(40, 30, 20), 1))
        painter.setBrush(color)
        margin = max(1, min(width, height) // 10)
        painter.drawEllipse(QRect(margin, margin, width - 2 * margin, height - 2 * margin))

        font = QFont()
        font.setPixelSize(max(6, min(width, height) // 5))
        painter.setFont(font)
        painter.setPen(QColor(20, 20, 20))
        painter.drawText(QRect(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, label)
    finally:
        painter.end()
    return image
