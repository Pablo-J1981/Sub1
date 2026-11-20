"""창과 모니터 상태를 일정 주기로 읽어 최신 스냅샷을 보관한다.

펫은 매 프레임 latest만 읽는다. 창 목록 조회는 이 객체에서만 일어난다.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QTimer

from core.world import WorldSnapshot
from platform_win.windows import read_world

log = logging.getLogger("desktop_pet")


class WorldPoller(QObject):
    def __init__(self, hz: float, min_surface_width: float, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._min_width = min_surface_width
        self.latest: WorldSnapshot = WorldSnapshot()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.setInterval(max(1, round(1000 / hz)))
        self._timer.timeout.connect(self.refresh)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def refresh(self) -> None:
        try:
            self.latest = read_world(self._min_width)
        except Exception:  # 창 조회 실패가 프로그램 종료로 이어지면 안 된다
            log.exception("창 상태 갱신 실패 (이전 상태를 유지합니다)")
