import random
from dataclasses import replace
from pathlib import Path

import pytest

from core.config import load_config
from core.geometry import MonitorInfo, Rect
from core.window_rules import RawWindow
from core.world import WorldSnapshot, build_snapshot
from pets.walker import WalkerPet, WalkerState

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "settings.json")

MON_RECT = Rect(0, 0, 1000, 800)
WORK = Rect(0, 0, 1000, 760)
MONITORS = [MonitorInfo(rect=MON_RECT, work=WORK)]
FLOOR_Y = 760


def raw(hwnd, l, t, r, b, **kw):
    base = dict(visible=True, iconic=False, zoomed=False, cloaked=False,
                tool=False, shell=False, own=False)
    base.update(kw)
    return RawWindow(hwnd=hwnd, rect=Rect(l, t, r, b), **base)


def world(*raws) -> WorldSnapshot:
    return build_snapshot(list(raws), MONITORS, CFG.physics.min_surface_width)


def make_pet(seed=0, **walker_overrides) -> WalkerPet:
    beh = replace(CFG.walker, **walker_overrides) if walker_overrides else CFG.walker
    return WalkerPet(
        width=64,
        ground_offset=56,
        unit=1.0,
        physics=CFG.physics,
        behavior=beh,
        rng=random.Random(seed),
    )


def run(pet, seconds, snap, dt=1 / 60):
    steps = int(seconds / dt)
    for _ in range(steps):
        pet.update(dt, snap)


# ----------------------------------------------------------------- 낙하와 착지

def test_pet_falls_and_lands_on_floor():
    pet = make_pet()
    pet.place(cx=500, feet_y=100)
    run(pet, 3.0, world())
    assert pet.feet_y == FLOOR_Y
    assert pet.is_grounded()
    assert pet.state is not WalkerState.FALL


def test_landing_is_not_triggered_when_moving_up():
    pet = make_pet()
    pet.place(cx=500, feet_y=700)
    pet.vy = -500  # 위로 튀는 중
    pet.update(1 / 60, world())
    assert pet.state is WalkerState.FALL


def test_pet_lands_on_window_top_not_below_it():
    pet = make_pet()
    snap = world(raw(1, 300, 400, 700, 600))
    pet.place(cx=500, feet_y=100)
    run(pet, 3.0, snap)
    assert pet.feet_y == 400  # 창 윗변에 착지
    assert pet.is_grounded()


def test_upper_window_is_landed_on_first():
    pet = make_pet()
    lower = raw(1, 300, 400, 700, 600)
    upper = raw(2, 400, 300, 600, 500)  # 위쪽 창이 펫 자리를 덮음
    pet.place(cx=500, feet_y=100)
    run(pet, 3.0, world(upper, lower))
    # 펫은 위쪽 창(윗변 300)에 먼저 닿는다. 아래 창(윗변 400)은 그 창에 가려진 구간이다.
    assert pet.feet_y == 300


# ----------------------------------------------------------------- 걷기와 방향

def test_walk_turns_at_monitor_wall_on_floor():
    pet = make_pet()
    pet.place(cx=500, feet_y=FLOOR_Y)
    run(pet, 0.5, world())
    pet.command("walk", direction=1, duration=1000)
    half = pet.half_width
    flips = 0
    last = pet.facing
    for _ in range(60 * 60):
        pet.update(1 / 60, world())
        assert pet.cx - half >= -1e-6 and pet.cx + half <= 1000 + 1e-6
        if pet.facing != last:
            flips += 1
            last = pet.facing
    assert flips >= 2  # 벽에 닿을 때마다 방향을 바꾼다
    assert pet.feet_y == FLOOR_Y


def test_floor_edge_does_not_make_pet_jump_off():
    pet = make_pet(jump_off_chance=1.0)
    pet.place(cx=900, feet_y=FLOOR_Y)
    run(pet, 0.5, world())
    pet.command("walk", direction=1, duration=1000)
    run(pet, 10, world())
    assert pet.feet_y == FLOOR_Y  # 바닥 끝에서는 뛰지 않는다
    assert pet.state is not WalkerState.JUMP_OFF


# ----------------------------------------------------------------- 가장자리 공포와 뛰어내리기

def _walk_to_window_edge(pet, snap, start_cx):
    pet.place(cx=start_cx, feet_y=400)
    run(pet, 0.5, snap)
    assert pet.feet_y == 400
    pet.command("walk", direction=1, duration=1000)


def test_window_edge_makes_pet_scared_first():
    pet = make_pet(jump_off_chance=0.0)
    snap = world(raw(1, 300, 400, 500, 600))
    _walk_to_window_edge(pet, snap, start_cx=400)
    for _ in range(int(20 * 60)):
        pet.update(1 / 60, snap)
        if pet.state is WalkerState.SCARED:
            break
    assert pet.state is WalkerState.SCARED
    assert pet.action() == "scared"


def test_scared_pet_jumps_off_when_chance_is_one():
    pet = make_pet(jump_off_chance=1.0)
    snap = world(raw(1, 300, 400, 500, 600))
    _walk_to_window_edge(pet, snap, start_cx=400)
    seen_jump = False
    for _ in range(int(30 * 60)):
        pet.update(1 / 60, snap)
        if pet.state is WalkerState.JUMP_OFF:
            seen_jump = True
            break
    assert seen_jump
    # 뛰어내린 뒤에는 같은 창 위에 다시 올라서지 않고 바닥에 떨어진다
    run(pet, 5, snap)
    assert pet.feet_y == FLOOR_Y


def test_scared_pet_turns_back_when_chance_is_zero():
    pet = make_pet(jump_off_chance=0.0)
    snap = world(raw(1, 300, 400, 500, 600))
    _walk_to_window_edge(pet, snap, start_cx=400)
    run(pet, 30, snap)
    assert pet.feet_y == 400  # 창 위에 그대로 있음
    assert pet.state is not WalkerState.JUMP_OFF


# ----------------------------------------------------------------- 창 따라가기와 놀람

def test_pet_moves_with_window():
    pet = make_pet()
    pet.place(cx=450, feet_y=400)
    run(pet, 0.5, world(raw(1, 300, 400, 600, 600)))
    before = pet.cx
    moved = world(raw(1, 350, 400, 650, 600))
    pet.update(1 / 60, moved)
    assert pet.cx == pytest.approx(before + 50)


def test_pet_follows_window_vertical_move():
    pet = make_pet()
    pet.place(cx=450, feet_y=400)
    run(pet, 0.5, world(raw(1, 300, 400, 600, 600)))
    pet.update(1 / 60, world(raw(1, 300, 350, 600, 550)))
    assert pet.feet_y == 350


def test_closed_window_startles_then_falls():
    pet = make_pet()
    pet.place(cx=450, feet_y=400)
    run(pet, 0.5, world(raw(1, 300, 400, 600, 600)))
    pet.update(1 / 60, world())  # 창이 사라졌다
    assert pet.state is WalkerState.STARTLED
    assert pet.action() == "scared"
    run(pet, CFG.walker.startled_duration_s + 0.1, world())
    assert pet.state in (WalkerState.FALL, WalkerState.LAND) or pet.is_grounded()
    run(pet, 3, world())
    assert pet.feet_y == FLOOR_Y


def test_maximized_window_startles_pet():
    pet = make_pet()
    pet.place(cx=450, feet_y=400)
    run(pet, 0.5, world(raw(1, 300, 400, 600, 600)))
    pet.update(1 / 60, world(raw(1, 300, 400, 600, 600, zoomed=True)))
    assert pet.state is WalkerState.STARTLED


def test_minimized_window_startles_pet():
    pet = make_pet()
    pet.place(cx=450, feet_y=400)
    run(pet, 0.5, world(raw(1, 300, 400, 600, 600)))
    pet.update(1 / 60, world(raw(1, 300, 400, 600, 600, iconic=True)))
    assert pet.state is WalkerState.STARTLED


def test_pet_falls_when_window_is_covered_not_startled():
    pet = make_pet()
    pet.place(cx=450, feet_y=400)
    run(pet, 0.5, world(raw(1, 300, 400, 600, 600)))
    covered = world(raw(2, 300, 300, 600, 500), raw(1, 300, 400, 600, 600))
    pet.update(1 / 60, covered)
    assert pet.state is WalkerState.FALL


# ----------------------------------------------------------------- 안정성

def test_large_dt_is_clamped():
    pet = make_pet()
    pet.place(cx=500, feet_y=100)
    before = pet.feet_y
    pet.update(10.0, world())
    step = CFG.physics.max_step_s
    # 낙하 1회 갱신: v = g*step, y 이동 = g*step*step
    assert pet.feet_y - before == pytest.approx(CFG.physics.gravity * step * step)


def test_command_rejected_while_falling():
    pet = make_pet()
    pet.place(cx=500, feet_y=100)
    assert pet.command("walk", direction=1) is False


def test_unknown_command_raises():
    pet = make_pet()
    pet.place(cx=500, feet_y=FLOOR_Y)
    with pytest.raises(ValueError):
        pet.command("fly")


def test_seeded_run_is_deterministic():
    def trace(seed):
        pet = make_pet(seed=seed)
        pet.place(cx=500, feet_y=FLOOR_Y)
        out = []
        for _ in range(60 * 60):
            pet.update(1 / 60, world())
            out.append((pet.state, round(pet.cx, 3)))
        return out

    assert trace(7) == trace(7)


# ----------------------------------------------------------------- 먹이 쪽으로 걷기

def test_walk_to_reaches_target_and_waits_there():
    pet = make_pet(seed=3)
    pet.place(cx=200, feet_y=100)
    snap = world()
    run(pet, 3.0, snap)  # 바닥에 내려앉는다
    target = 600.0
    assert pet.walk_to(target) is True
    run(pet, 20.0, snap)
    assert pet.arrived()
    assert pet.cx == pytest.approx(target)
    assert pet.begin_eat(2.0) is True
    assert pet.is_eating()
    run(pet, 2.5, snap)
    assert pet.take_meal() is True
    assert pet.take_meal() is False  # 한 번만 알린다


def test_walk_to_is_refused_when_frozen_or_airborne():
    pet = make_pet(seed=4)
    pet.place(cx=200, feet_y=100)
    assert pet.walk_to(300) is False  # 아직 공중이다
    run(pet, 3.0, world())
    pet.set_frozen(True)
    assert pet.walk_to(300) is False
