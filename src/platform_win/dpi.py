"""Per-Monitor DPI v2 설정 (Windows 전용, 다른 OS에서는 아무 일도 하지 않음)."""

from __future__ import annotations

import ctypes
import sys

# Win32 상수: DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
_PER_MONITOR_AWARE_V2 = -4


def enable_per_monitor_dpi_v2() -> bool:
    """프로세스를 Per-Monitor DPI v2로 설정한다.

    QApplication을 만들기 전에 호출해야 한다. 이미 Qt가 설정한 뒤라면
    실패할 수 있으나 그 경우에도 Qt가 같은 모드로 동작하므로 무해하다.
    """
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
    return bool(user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(_PER_MONITOR_AWARE_V2)))
