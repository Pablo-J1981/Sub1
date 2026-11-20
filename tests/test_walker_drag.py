"""드래그로 들기, 놓기, 던지기에 대한 WalkerPet 테스트."""

from pathlib import Path

from core.config import load_config
from core.geometry import MonitorInfo, Rect
from core.world import build_snapshot
from pets.walker import WalkerPet, WalkerState

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "settings.json")
WORK = Rect(0, 0, 1000, 760)
WORLD = build_snapshot([], [MonitorInfo(rect=Rect(0, 0, 1000, 800), work=WORK)], 24)


def make_pet():
    return WalkerPet(
        width=64, ground_offset=56, unit=1.0,
        physics=CFG.physics, behavior=CFG.walker,
        rng=__import__("random").Random(0),
    )


def run(pet, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        pet.update(dt, WORLD)


def test_held_pet_follows_position_and_ignores_gravity():
    pet = make_pet()
    pet.place(cx=500, feet_y=100)
    pet.update(1 / 60, WORLD)
    pet.hold(300, 200)
    run(pet, 1.0)
    assert pet.state is WalkerState.HELD
    assert (pet.cx, pet.feet_y) == (300, 200)
    assert pet.action() == "held"


def test_held_position_is_clamped_to_work_area():
    pet = make_pet()
    pet.place(cx=500, feet_y=100)
    pet.update(1 / 60, WORLD)
    pet.hold(-500, 5000)
    assert pet.cx >= 32            # 작업 영역 왼쪽 벽 안쪽
    assert pet.feet_y == WORK.bottom  # 작업 표시줄 위


def test_release_throws_and_lands_on_floor():
    pet = make_pet()
    pet.place(cx=300, feet_y=300)
    pet.update(1 / 60, WORLD)
    pet.hold(300, 300)
    pet.release(vx=200, vy=-300)
    assert pet.state is WalkerState.FALL
    run(pet, 4.0)
    assert pet.is_grounded()
    assert pet.feet_y == WORK.bottom
    assert pet.cx > 300  # 던진 방향으로 밀려났다


def test_release_while_not_held_is_ignored():
    pet = make_pet()
    pet.place(cx=500, feet_y=100)
    before = pet.state
    pet.release(vx=999, vy=999)
    assert pet.state is before
    assert pet.vx == 0.0


def test_petting_grounded_pet_makes_it_idle_for_a_while():
    pet = make_pet()
    pet.place(cx=500, feet_y=100)
    run(pet, 3.0)
    pet.on_petted(3.0)
    assert pet.state is WalkerState.IDLE
    assert pet.timer == 3.0
