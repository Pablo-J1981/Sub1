"""마우스 입력 판정 테스트 (Qt 비의존, 순수 로직)."""

import pytest

from core.pointer import PetPointer, StrokeDetector, ThrowTracker, throw_velocity


def make_pointer(**overrides):
    params = dict(
        drag_threshold=4, min_stroke=20, throw_inertia=0.8,
        max_throw_speed=1200, velocity_window_s=0.1,
    )
    params.update(overrides)
    return PetPointer(**params)


# ----------------------------------------------------------------- 던지기 속도

def test_velocity_is_average_over_recent_window():
    tr = ThrowTracker(0.1)
    tr.add(0.00, 100, 0)
    tr.add(0.05, 110, 0)
    tr.add(0.10, 120, 0)
    vx, vy = tr.velocity(0.10)
    assert vx == pytest.approx(200.0)
    assert vy == 0


def test_old_samples_are_ignored():
    tr = ThrowTracker(0.1)
    tr.add(0.0, 0, 0)
    tr.add(1.0, 500, 0)  # 0.0 샘플은 window 밖이다
    tr.add(1.05, 510, 0)
    assert tr.velocity(1.05)[0] == pytest.approx(200.0)


def test_stopped_cursor_gives_zero_velocity():
    tr = ThrowTracker(0.1)
    tr.add(0.0, 0, 0)
    tr.add(0.02, 50, 0)
    # 0.5초 동안 아무 샘플도 없으면 멈춘 것으로 본다
    assert tr.velocity(0.5) == (0.0, 0.0)


def test_throw_velocity_applies_inertia_and_cap():
    vx, vy = throw_velocity(1000, 0, inertia=0.5, max_speed=300)
    assert vx == pytest.approx(300)  # 500 -> 상한 300
    assert vy == 0
    vx, vy = throw_velocity(100, -100, inertia=1.0, max_speed=1000)
    assert (vx, vy) == pytest.approx((100, -100))


# ----------------------------------------------------------------- 쓰다듬기

def test_stroke_counts_one_full_back_and_forth():
    det = StrokeDetector(min_travel=20)
    results = [det.feed(x) for x in (0, 10, 25, 15, 0, -10)]
    # 0->25 (오른쪽 25) 후 방향이 바뀌는 순간 한 번 센다
    assert sum(results) == 1


def test_small_jitter_is_not_a_stroke():
    det = StrokeDetector(min_travel=20)
    results = [det.feed(x) for x in (0, 5, 0, 5, 0, 5, 0)]
    assert not any(results)


def test_pet_counts_strokes_only_while_hovering():
    p = make_pointer()
    p.hover(False)
    xs = [100, 150, 100, 150, 100, 150]
    assert not any(p.poll(i * 0.01, x, 0).petted for i, x in enumerate(xs))
    p.hover(True)
    got = [p.poll(1 + i * 0.01, x, 0).petted for i, x in enumerate(xs)]
    assert sum(got) >= 1


# ----------------------------------------------------------------- 드래그

def test_small_move_is_not_drag():
    p = make_pointer()
    p.press(100, 100, cx=100, feet_y=160)
    res = p.poll(0.0, 102, 101)  # 거리 약 2.2 < 4
    assert res.hold is None
    assert not p.dragging
    assert p.release(0.01, 102, 101) is None


def test_drag_follows_cursor_with_grab_offset():
    p = make_pointer()
    # 펫의 발 위치가 커서보다 (+0, +60) 아래에 있다고 가정하고 눌렀다
    p.press(100, 100, cx=100, feet_y=160)
    res = p.poll(0.0, 130, 120)
    assert res.hold == pytest.approx((130, 180))
    assert p.dragging


def test_release_returns_throw_velocity():
    p = make_pointer(throw_inertia=1.0)
    p.press(100, 100, cx=100, feet_y=160)
    t = 0.0
    for step in range(1, 6):
        t = step * 0.01
        p.poll(t, 100 + step * 10, 100)  # 초당 1000px 로 이동
    v = p.release(t, 150, 100)
    assert v is not None
    assert v[0] == pytest.approx(1000, rel=0.05)
    assert v[1] == pytest.approx(0)
    assert not p.pressed


def test_release_without_drag_has_no_velocity():
    p = make_pointer()
    p.press(100, 100, cx=100, feet_y=160)
    assert p.release(0.5, 100, 100) is None
