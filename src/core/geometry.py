"""화면 기하 계산: 사각형, 모니터, 발판(표면) 계산. Qt에 의존하지 않는다.

좌표: 물리(디바이스) 픽셀, 원점은 주 모니터 왼쪽 위, y는 아래로 증가.
발판(Surface)은 "펫이 설 수 있는 수평 선분"이다.
- 작업 영역 바닥(작업 표시줄 윗변): owner=None
- 가려지지 않은 일반 창의 윗변: owner=창 핸들
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def intersects(self, other: "Rect") -> bool:
        return (
            self.left < other.right
            and other.left < self.right
            and self.top < other.bottom
            and other.top < self.bottom
        )


@dataclass(frozen=True)
class MonitorInfo:
    rect: Rect  # 모니터 전체 영역
    work: Rect  # 작업 영역 (작업 표시줄 제외)


@dataclass(frozen=True)
class WindowInfo:
    """z순서 목록의 한 항목. 목록은 가장 위에 있는 창부터 정렬되어 있어야 한다."""

    hwnd: int
    rect: Rect
    is_surface: bool  # True면 발판 후보, False면 가림막 역할만 한다


@dataclass(frozen=True)
class Surface:
    owner: int | None  # None이면 작업 영역 바닥
    left: int          # 가려지지 않은 구간의 왼쪽 (x)
    right: int         # 가려지지 않은 구간의 오른쪽 (x, 배타적)
    y: int             # 발판 윗변 y
    owner_left: int    # 소유 창 전체의 왼쪽 x (창 이동 추적용, 가림과 무관)
    monitor: Rect      # 이 발판이 속한 모니터 전체 영역

    @property
    def is_floor(self) -> bool:
        return self.owner is None


def subtract_intervals(
    left: float,
    right: float,
    cuts: Iterable[tuple[float, float]],
) -> list[tuple[float, float]]:
    """[left, right) 구간에서 cuts 구간들을 빼고 남은 조각들을 반환한다."""
    pieces: list[tuple[float, float]] = [(left, right)]
    for c_left, c_right in sorted(cuts):
        next_pieces: list[tuple[float, float]] = []
        for a, b in pieces:
            if c_right <= a or c_left >= b:
                next_pieces.append((a, b))
                continue
            if c_left > a:
                next_pieces.append((a, c_left))
            if c_right < b:
                next_pieces.append((c_right, b))
        pieces = next_pieces
    return [(a, b) for a, b in pieces if b > a]


def compute_surfaces(
    windows: Sequence[WindowInfo],
    monitor: MonitorInfo,
    min_width: float,
) -> list[Surface]:
    """한 모니터 위의 발판 목록을 계산한다.

    - 바닥: 작업 영역 바닥. 일반 창에 가려지지 않는다(작업 표시줄은 항상 위에 있음).
    - 창: 윗변 구간에서 z순서상 위에 있는 창(가림막 포함)이 덮은 부분을 뺀다.
    - 모니터 밖으로 나간 부분은 모니터 안쪽만 발판이 된다.
    - min_width보다 짧은 조각은 발판으로 쓰지 않는다.
    """
    mon = monitor.rect
    work = monitor.work
    result: list[Surface] = []

    if work.width >= min_width:
        result.append(Surface(None, work.left, work.right, work.bottom, work.left, mon))

    for i, win in enumerate(windows):
        if not win.is_surface:
            continue
        r = win.rect
        y = r.top
        if y < mon.top or y >= work.bottom:
            continue
        if not r.intersects(mon):
            continue
        left = max(r.left, mon.left)
        right = min(r.right, mon.right)
        if right - left < min_width:
            continue

        cuts: list[tuple[float, float]] = []
        for upper in windows[:i]:
            o = upper.rect
            # 위쪽 창이 이 윗변 높이를 덮고 있으면 그 x구간은 가려진 것이다
            if o.top <= y < o.bottom and o.left < right and left < o.right:
                cuts.append((o.left, o.right))

        for a, b in subtract_intervals(left, right, cuts):
            if b - a >= min_width:
                result.append(Surface(win.hwnd, a, b, y, r.left, mon))

    return result


def spawn_point(work: Rect, spawn_height: float, factor: float) -> tuple[float, float]:
    """펫을 처음 놓을 (cx, feet_y). 작업 영역 가운데, 발판(작업 영역 바닥)에서 위로 띄운 곳.

    feet_y는 발판 윗변 y(= work.bottom)를 기준으로 한다. work.top을 쓰면 화면 위 밖에서 떨어진다.
    """
    return (work.left + work.width / 2, work.bottom - spawn_height * factor)
