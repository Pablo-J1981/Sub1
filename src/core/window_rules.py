"""창 분류 규칙 (Qt/Win32 비의존).

Win32 쪽(platform_win/windows.py)이 읽은 창 상태를 RawWindow로 넘기면,
여기서 이 창이 발판인지, 가림막인지, 무시할 창인지 결정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from core.geometry import Rect, WindowInfo


class WindowRole(Enum):
    IGNORE = "ignore"      # 목록에서 완전히 제외
    OCCLUDER = "occluder"  # 가리기만 함 (최대화 창, 도구 창)
    SURFACE = "surface"    # 발판 후보이면서 가림막


@dataclass(frozen=True)
class RawWindow:
    hwnd: int
    rect: Rect          # DWM 확장 프레임 경계 (물리 픽셀)
    visible: bool       # IsWindowVisible
    iconic: bool        # 최소화
    zoomed: bool        # 최대화
    cloaked: bool       # DWM 숨김(다른 가상 데스크톱 등)
    tool: bool          # WS_EX_TOOLWINDOW
    shell: bool         # 바탕화면/작업 표시줄 등 셸 창
    own: bool           # 이 프로그램이 만든 창


def classify_window(w: RawWindow) -> WindowRole:
    """발판 규칙:
    - 보이지 않음, 최소화, 숨김(cloaked), 자기 창, 셸 창은 무시한다.
    - 최대화 창과 도구 창은 가리기만 하고 발판이 되지 않는다.
    - 나머지 창은 발판 후보이면서 가림막이 된다.
    """
    if not w.visible or w.iconic or w.cloaked or w.own or w.shell:
        return WindowRole.IGNORE
    if w.rect.width <= 0 or w.rect.height <= 0:
        return WindowRole.IGNORE
    if w.zoomed or w.tool:
        return WindowRole.OCCLUDER
    return WindowRole.SURFACE


def to_window_infos(raws: Sequence[RawWindow]) -> list[WindowInfo]:
    """z순서(위에 있는 창부터)를 유지하며 발판 계산용 목록으로 바꾼다."""
    infos: list[WindowInfo] = []
    for raw in raws:
        role = classify_window(raw)
        if role is WindowRole.IGNORE:
            continue
        infos.append(WindowInfo(hwnd=raw.hwnd, rect=raw.rect, is_surface=role is WindowRole.SURFACE))
    return infos
