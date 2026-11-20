from core.geometry import MonitorInfo, Rect, WindowInfo, compute_surfaces, subtract_intervals

MON = MonitorInfo(rect=Rect(0, 0, 1000, 800), work=Rect(0, 0, 1000, 760))


def win(hwnd, l, t, r, b, surface=True):
    return WindowInfo(hwnd=hwnd, rect=Rect(l, t, r, b), is_surface=surface)


def test_subtract_no_cuts():
    assert subtract_intervals(0, 10, []) == [(0, 10)]


def test_subtract_middle_and_edges():
    assert subtract_intervals(0, 10, [(2, 4), (6, 8)]) == [(0, 2), (4, 6), (8, 10)]


def test_subtract_full_cover_and_overlap():
    assert subtract_intervals(0, 10, [(-5, 20)]) == []
    assert subtract_intervals(0, 10, [(5, 15)]) == [(0, 5)]


def test_floor_is_always_a_surface():
    surfaces = compute_surfaces([], MON, min_width=24)
    assert len(surfaces) == 1
    s = surfaces[0]
    assert s.is_floor and s.y == 760 and (s.left, s.right) == (0, 1000)


def test_window_top_is_surface():
    surfaces = compute_surfaces([win(1, 100, 300, 400, 600)], MON, min_width=24)
    window_surfaces = [s for s in surfaces if not s.is_floor]
    assert len(window_surfaces) == 1
    assert (window_surfaces[0].left, window_surfaces[0].right, window_surfaces[0].y) == (100, 400, 300)


def test_upper_window_hides_part_of_top_edge():
    # 위쪽 창(1)이 아래 창(2)의 윗변 중간을 가린다
    windows = [win(1, 200, 250, 300, 500), win(2, 100, 300, 400, 600)]
    surfaces = [s for s in compute_surfaces(windows, MON, min_width=10) if s.owner == 2]
    assert [(s.left, s.right) for s in surfaces] == [(100, 200), (300, 400)]


def test_lower_window_does_not_hide_upper_window():
    windows = [win(1, 100, 300, 400, 600), win(2, 200, 250, 300, 500)]
    surfaces = [s for s in compute_surfaces(windows, MON, min_width=10) if s.owner == 1]
    assert [(s.left, s.right) for s in surfaces] == [(100, 400)]


def test_short_pieces_are_dropped():
    # 창 2의 윗변 x 100~230 중 위쪽 창 1이 200~300을 가린다.
    # 남는 조각은 100~200(100px)뿐이고, 최소 폭 150 미만이므로 버려진다.
    windows = [win(1, 200, 250, 300, 500), win(2, 100, 300, 230, 600)]
    surfaces = [s for s in compute_surfaces(windows, MON, min_width=150) if s.owner == 2]
    assert surfaces == []


def test_piece_at_least_min_width_is_kept():
    windows = [win(1, 200, 250, 300, 500), win(2, 100, 300, 230, 600)]
    surfaces = [s for s in compute_surfaces(windows, MON, min_width=40) if s.owner == 2]
    assert [(s.left, s.right) for s in surfaces] == [(100, 200)]


def test_non_surface_window_only_occludes():
    windows = [win(1, 200, 250, 300, 500, surface=False), win(2, 100, 300, 400, 600)]
    surfaces = [s for s in compute_surfaces(windows, MON, min_width=10) if s.owner == 2]
    assert [(s.left, s.right) for s in surfaces] == [(100, 200), (300, 400)]


def test_window_above_monitor_top_is_skipped():
    surfaces = compute_surfaces([win(1, 100, -50, 400, 300)], MON, min_width=10)
    assert all(s.owner is None for s in surfaces)


def test_owner_left_is_kept_even_when_hidden():
    windows = [win(1, 200, 250, 300, 500), win(2, 100, 300, 400, 600)]
    owned = [s for s in compute_surfaces(windows, MON, min_width=10) if s.owner == 2]
    assert all(s.owner_left == 100 for s in owned)


def test_work_area_excludes_taskbar_on_floor():
    mon = MonitorInfo(rect=Rect(0, 0, 1000, 800), work=Rect(0, 0, 1000, 760))
    floor = [s for s in compute_surfaces([], mon, 24) if s.is_floor][0]
    assert floor.y == 760  # 작업 표시줄 윗변, 모니터 바닥(800)이 아님


def test_spawn_point_is_above_floor_not_screen_top():
    from core.geometry import spawn_point

    work = Rect(0, 0, 1000, 760)
    cx, feet = spawn_point(work, spawn_height=150, factor=4)
    assert cx == 500
    assert feet == 760 - 600  # 발판(바닥 760)에서 위로 600px
    assert feet > work.top  # 화면 위 밖이 아니다
