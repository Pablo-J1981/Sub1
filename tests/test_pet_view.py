"""PetView 통합 스모크 테스트 (오프스크린 Qt, 고정된 가짜 세계 사용)."""

import os
import random
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.config import load_config  # noqa: E402
from core.geometry import MonitorInfo, Rect  # noqa: E402
from core.mood import Mood  # noqa: E402
from core.needs import Needs  # noqa: E402
from core.pet_spec import load_pet_spec, parse_pet_spec  # noqa: E402
from core.pointer import PetPointer  # noqa: E402
from core.world import build_snapshot  # noqa: E402
from pets import create_pet  # noqa: E402
from ui.pet_view import PetView  # noqa: E402
from ui.sprites import SpriteBank  # noqa: E402
from ui.world_poller import WorldPoller  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "settings.json")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeCursor:
    def __init__(self, x=0, y=0):
        self.x, self.y = x, y

    def __call__(self):
        return (self.x, self.y)


def _make_view(seed=1, cursor=None, time_scale=1.0, food=False):
    spec = load_pet_spec(ROOT / "assets" / "pets" / "dog")
    sprites = SpriteBank(spec)
    sprites.load()
    body = create_pet(
        "walker", width=52, ground_offset=46, unit=1.0,
        physics=CFG.physics, behavior=CFG.walker, rng=random.Random(seed),
    )
    poller = WorldPoller(CFG.physics.window_poll_hz, CFG.physics.min_surface_width)
    mon = MonitorInfo(rect=Rect(0, 0, 1000, 800), work=Rect(0, 0, 1000, 760))
    poller.latest = build_snapshot([], [mon], CFG.physics.min_surface_width)
    pointer = PetPointer(
        drag_threshold=CFG.pointer.drag_threshold_px,
        min_stroke=CFG.pointer.min_stroke_px,
        throw_inertia=CFG.pointer.throw_inertia,
        max_throw_speed=CFG.pointer.max_throw_speed,
        velocity_window_s=CFG.pointer.velocity_window_s,
    )
    food_image = QImage(str(ROOT / "assets" / "items" / "food_bowl.png")) if food else None
    view = PetView(
        body, spec, sprites, poller, pet_scale=1, fps=60,
        mood=Mood(CFG.mood), pointer=pointer,
        needs=Needs(CFG.needs), food_image=food_image, time_scale=time_scale,
        max_step_s=CFG.physics.max_step_s,
        cursor=cursor if cursor is not None else FakeCursor(),
    )
    view.spawn(500, 100)
    return view


def spec_walk_frames():
    return load_pet_spec(ROOT / "assets" / "pets" / "dog").actions["walk"].frames


def _run(view, seconds, start=0.0):
    t = start
    for _ in range(int(seconds * 60)):
        t += 1 / 60
        view.advance(t)
    return t


def test_dog_sprites_load_without_placeholders(qapp):
    spec = load_pet_spec(ROOT / "assets" / "pets" / "dog")
    bank = SpriteBank(spec)
    bank.load()
    assert bank.missing == []
    assert bank.frame("idle", 0).width() == 52
    assert bank.frame("walk", 0).height() == 52
    assert bank.tomb().width() == 52
    assert spec_walk_frames() == 8


def test_missing_files_fall_back_to_placeholders(qapp, tmp_path, monkeypatch):
    import json

    data = json.loads((ROOT / "assets" / "pets" / "dog" / "pet.json").read_text(encoding="utf-8"))
    spec = parse_pet_spec("empty", data, tmp_path)  # 그림 파일이 하나도 없다
    bank = SpriteBank(spec)
    bank.load()
    assert set(bank.missing) == set(spec.actions) | {"tomb"}
    assert bank.frame("walk", 0).width() == 52


def test_view_falls_and_lands_on_floor(qapp):
    view = _make_view()
    _run(view, 4.0)
    assert view._body.feet_y == pytest.approx(760)
    assert view._body.is_grounded()


def test_view_mirrors_art_when_facing_left(qapp):
    view = _make_view()
    _run(view, 4.0)
    view._body.facing = -1
    _run(view, 0.1, start=4.0)
    assert view._art_key is not None and view._art_key[2] == -1


def test_view_does_not_rebuild_art_every_frame(qapp):
    view = _make_view()
    _run(view, 4.0)
    view._body.command("sit", duration=10.0)  # 시간이 지나도 동작이 바뀌지 않도록 고정
    t = _run(view, 0.1, start=4.0)
    rebuilds = []
    original = view.set_art
    view.set_art = lambda image, scale: (rebuilds.append(1), original(image, scale))
    _run(view, 0.5, start=t)  # sit 는 1fps, 2프레임: 0.5초 동안 그림은 최대 한 번만 바뀐다
    assert len(rebuilds) <= 1
    assert view._art_key[0] == "sit"


def test_advance_survives_empty_world(qapp):
    view = _make_view()
    view._poller.latest = build_snapshot([], [], CFG.physics.min_surface_width)
    _run(view, 1.0)  # 모니터가 없으면 물리 갱신을 건너뛰고 죽지 않는다
    assert view._body.feet_y == 100  # 낙하하지 않고 그대로 있다


def test_time_scale_speeds_up_needs_and_mood(qapp):
    slow = _make_view(time_scale=1.0)
    fast = _make_view(time_scale=4.0)
    _run(slow, 10.0)
    _run(fast, 10.0)
    assert fast.needs.fullness < slow.needs.fullness
    assert fast.mood.value != slow.mood.value


def test_real_clock_jump_is_capped(qapp):
    view = _make_view()
    view.advance(0.0)
    view.advance(60.0)  # 한 번에 60초가 지난 것처럼 보여도 펫은 한 번에 크게 튀지 않는다
    assert view.needs.fullness > CFG.needs.start - 1.0


def test_food_is_eaten_and_refills_hunger(qapp):
    view = _make_view(food=True)
    _run(view, 4.0)
    view.needs.fullness = 5.0
    assert view.feed() is True
    _run(view, 60.0)  # 걸어가서 먹고 돌아올 만큼 기다린다
    assert view.needs.fullness > 5.0
    assert not view._feeding.has_food


def test_feed_is_refused_without_food_image(qapp):
    view = _make_view(food=False)
    _run(view, 4.0)
    assert view.feed() is False


def test_death_shows_die_then_tomb_and_freezes(qapp):
    view = _make_view()
    _run(view, 4.0)
    view.needs.fullness = 0.0
    view.needs.dead = True
    t = _run(view, 0.1, start=4.0)
    cx_before = view._body.cx
    assert view._art_key[0] == "die"
    t = _run(view, 3.0, start=t)
    assert view._art_key[0] == "tomb"
    assert view._body.cx == cx_before  # 죽은 뒤에는 움직이지 않는다


def test_restart_revives_and_resets_mood(qapp):
    view = _make_view()
    _run(view, 4.0)
    view.needs.dead = True
    t = _run(view, 3.0, start=4.0)
    assert view._art_key[0] == "tomb"
    view.restart(300, 200)
    assert view.needs.dead is False
    assert view.needs.fullness == CFG.needs.start
    assert view.mood.value == CFG.mood.start
    _run(view, 0.2, start=t)
    assert view._art_key[0] != "tomb"
    assert view._body.cx == 300


def test_death_while_held_drops_the_pet(qapp):
    view = _make_view()
    _run(view, 4.0)
    view._body.hold(500, 300)  # 드래그로 들고 있는 중
    assert view._body.is_held()
    view.needs.dead = True
    view._step_needs(0.0, 5.0)  # 사망 처리 (시간 진행 없이 상태만 확인)
    view.finish_drag(5.0)
    _run(view, 3.0, start=5.0)
    assert not view._body.is_held()
    assert view._body.is_grounded()
