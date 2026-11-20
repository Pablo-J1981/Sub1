from core.geometry import Rect
from core.window_rules import RawWindow, WindowRole, classify_window, to_window_infos

R = Rect(0, 0, 300, 200)


def raw(**kw):
    base = dict(hwnd=1, rect=R, visible=True, iconic=False, zoomed=False,
                cloaked=False, tool=False, shell=False, own=False)
    base.update(kw)
    return RawWindow(**base)


def test_normal_window_is_surface():
    assert classify_window(raw()) is WindowRole.SURFACE


def test_invisible_minimized_cloaked_own_shell_are_ignored():
    for kw in ({"visible": False}, {"iconic": True}, {"cloaked": True},
               {"own": True}, {"shell": True}):
        assert classify_window(raw(**kw)) is WindowRole.IGNORE, kw


def test_zero_size_is_ignored():
    assert classify_window(raw(rect=Rect(0, 0, 0, 10))) is WindowRole.IGNORE


def test_maximized_and_tool_windows_only_occlude():
    assert classify_window(raw(zoomed=True)) is WindowRole.OCCLUDER
    assert classify_window(raw(tool=True)) is WindowRole.OCCLUDER


def test_to_window_infos_keeps_z_order_and_drops_ignored():
    raws = [
        raw(hwnd=10, rect=Rect(0, 0, 10, 10)),
        raw(hwnd=11, iconic=True),
        raw(hwnd=12, zoomed=True),
        raw(hwnd=13),
    ]
    infos = to_window_infos(raws)
    assert [i.hwnd for i in infos] == [10, 12, 13]
    assert [i.is_surface for i in infos] == [True, False, True]
