"""한 시점의 세계 상태 스냅샷 (Qt/Win32 비의존).

창 목록을 갱신할 때마다 새로 만들고, 펫은 이 스냅샷만 보고 움직인다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from core.geometry import MonitorInfo, Rect, Surface, compute_surfaces
from core.window_rules import RawWindow, to_window_infos


@dataclass(frozen=True)
class WorldSnapshot:
    monitors: tuple[MonitorInfo, ...] = ()
    surfaces: tuple[Surface, ...] = ()
    # 현재 발판 자격이 있는 창(보이고, 최소화/최대화/숨김이 아님)의 핸들 모음.
    # 가려져서 발판 구간이 0이어도 창 자체가 살아 있으면 여기에 들어 있다.
    surface_owners: frozenset[int] = field(default_factory=frozenset)

    def surfaces_on(self, monitor: Rect) -> list[Surface]:
        return [s for s in self.surfaces if s.monitor == monitor]

    def has_surface_window(self, hwnd: int) -> bool:
        return hwnd in self.surface_owners

    def monitor_for(self, x: float) -> MonitorInfo | None:
        """x 좌표가 속한 모니터. 어디에도 없으면 가장 가까운 모니터."""
        if not self.monitors:
            return None
        for mon in self.monitors:
            if mon.rect.left <= x < mon.rect.right:
                return mon

        def distance(mon: MonitorInfo) -> float:
            if x < mon.rect.left:
                return mon.rect.left - x
            return x - mon.rect.right

        return min(self.monitors, key=distance)


def build_snapshot(
    raws: Sequence[RawWindow],
    monitors: Sequence[MonitorInfo],
    min_surface_width: float,
) -> WorldSnapshot:
    """raws는 z순서(가장 위 창이 먼저)로 정렬되어 있어야 한다."""
    infos = to_window_infos(raws)
    surfaces: list = []
    for mon in monitors:
        surfaces.extend(compute_surfaces(infos, mon, min_surface_width))
    owners = frozenset(info.hwnd for info in infos if info.is_surface)
    return WorldSnapshot(
        monitors=tuple(monitors),
        surfaces=tuple(surfaces),
        surface_owners=owners,
    )
