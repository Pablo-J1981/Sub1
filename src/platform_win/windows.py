"""Windows 창/모니터 조회와 펫 창 이동 (Win32 ctypes).

다른 OS에서는 빈 결과를 반환해 프로그램이 죽지 않게 한다.
좌표는 모두 물리 픽셀이다 (프로세스가 Per-Monitor DPI v2로 설정된 상태를 전제).
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

from core.geometry import MonitorInfo, Rect
from core.window_rules import RawWindow
from core.world import WorldSnapshot, build_snapshot

IS_WINDOWS = sys.platform == "win32"

# 발판이 될 수 없는 셸 창 클래스 (바탕화면, 작업 표시줄)
SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi")

    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _MONENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(_RECT),
        wintypes.LPARAM,
    )

    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.IsZoomed.argtypes = [wintypes.HWND]
    _user32.IsZoomed.restype = wintypes.BOOL
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.EnumDisplayMonitors.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, _MONENUMPROC, wintypes.LPARAM,
    ]
    _user32.EnumDisplayMonitors.restype = wintypes.BOOL
    _user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
    _user32.GetMonitorInfoW.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _user32.SetWindowPos.restype = wintypes.BOOL

    # 세 번째 인자는 여러 구조체 포인터를 받으므로 argtypes를 지정하지 않고 byref로 넘긴다
    _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long  # HRESULT


def _to_rect(r: _RECT) -> Rect:
    return Rect(r.left, r.top, r.right, r.bottom)


def _frame_rect(hwnd: int) -> Rect:
    """DWM 확장 프레임 경계 (그림자 제외). 실패하면 GetWindowRect."""
    r = _RECT()
    hr = _dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)
    )
    if hr != 0:
        _user32.GetWindowRect(hwnd, ctypes.byref(r))
    return _to_rect(r)


def _is_cloaked(hwnd: int) -> bool:
    value = wintypes.DWORD(0)
    hr = _dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
    )
    return hr == 0 and value.value != 0


def _describe(hwnd: int, own_pid: int) -> RawWindow:
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    class_buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, class_buf, 256)

    ex_style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    return RawWindow(
        hwnd=int(hwnd),
        rect=_frame_rect(hwnd),
        visible=bool(_user32.IsWindowVisible(hwnd)),
        iconic=bool(_user32.IsIconic(hwnd)),
        zoomed=bool(_user32.IsZoomed(hwnd)),
        cloaked=_is_cloaked(hwnd),
        tool=bool(ex_style & WS_EX_TOOLWINDOW),
        shell=class_buf.value in SHELL_CLASSES,
        own=pid.value == own_pid,
    )


def enumerate_raw_windows() -> list[RawWindow]:
    """z순서(가장 위 창 먼저)대로 최상위 창 정보를 모은다."""
    if not IS_WINDOWS:
        return []
    own_pid = os.getpid()
    raws: list[RawWindow] = []

    def _callback(hwnd, _lparam):
        try:
            raws.append(_describe(hwnd, own_pid))
        except OSError:
            pass  # 한 창을 읽지 못해도 나머지 창 목록은 계속 만든다
        return True

    callback = _WNDENUMPROC(_callback)
    _user32.EnumWindows(callback, 0)
    return raws


def enumerate_monitors() -> list[MonitorInfo]:
    if not IS_WINDOWS:
        return []
    monitors: list[MonitorInfo] = []

    def _callback(hmonitor, _hdc, _lprect, _lparam):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if _user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            monitors.append(MonitorInfo(
                rect=_to_rect(info.rcMonitor),
                work=_to_rect(info.rcWork),
            ))
        return True

    callback = _MONENUMPROC(_callback)
    _user32.EnumDisplayMonitors(None, None, callback, 0)
    return monitors


def read_world(min_surface_width: float) -> WorldSnapshot:
    """현재 창과 모니터 상태를 한 번에 읽어 스냅샷으로 만든다."""
    return build_snapshot(enumerate_raw_windows(), enumerate_monitors(), min_surface_width)


def move_window(hwnd: int, x: int, y: int) -> None:
    """창의 왼쪽 위 좌표를 물리 픽셀로 옮긴다. 활성화와 z순서는 바꾸지 않는다."""
    if not IS_WINDOWS:
        return
    _user32.SetWindowPos(
        hwnd, None, int(x), int(y), 0, 0,
        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
    )
