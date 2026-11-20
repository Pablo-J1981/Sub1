"""창의 클릭 가능 영역을 Win32 창 영역(region)으로 지정한다.

불투명 픽셀 구간 목록(run)을 받아 합집합 영역을 만들고 SetWindowRgn으로 적용한다.
영역 밖 픽셀은 뒤쪽 창으로 클릭이 통과한다.
좌표는 물리(디바이스) 픽셀 기준이며, 창 왼쪽 위가 (0, 0)이다.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from core.render_math import Run

_RGN_OR = 2


def _load_win32():
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
    gdi32.CreateRectRgn.restype = wintypes.HANDLE
    gdi32.CombineRgn.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE, ctypes.c_int]
    gdi32.CombineRgn.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL

    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    user32.SetWindowRgn.restype = ctypes.c_int
    return gdi32, user32


def build_region_handle(runs: list[Run]) -> int:
    """구간 목록으로 Win32 HRGN을 만든다. 반환된 핸들은 호출자가 소유한다."""
    gdi32, _ = _load_win32()
    combined = gdi32.CreateRectRgn(0, 0, 0, 0)
    for y, x0, x1 in runs:
        rect = gdi32.CreateRectRgn(x0, y, x1, y + 1)
        gdi32.CombineRgn(combined, combined, rect, _RGN_OR)
        gdi32.DeleteObject(rect)
    return combined


def set_click_region(hwnd: int, runs: list[Run]) -> bool:
    """hwnd 창의 클릭 영역을 runs 기준으로 설정한다.

    성공 시 영역 핸들의 소유권은 시스템으로 넘어간다.
    Windows가 아니면 아무 일도 하지 않고 False를 반환한다.
    """
    if sys.platform != "win32":
        return False
    _, user32 = _load_win32()
    region = build_region_handle(runs)
    # SetWindowRgn 성공 시 region 핸들은 시스템이 관리하므로 직접 해제하지 않는다.
    return bool(user32.SetWindowRgn(hwnd, region, True))
