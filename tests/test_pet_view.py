"""PetView 통합 스모크 테스트 (오프스크린 Qt, 고정된 가짜 세계 사용)."""

import os
import random
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.config import load_config  # noqa: E402
from core.feeding import FoodPool  # noqa: E402
from core.geometry import MonitorInfo, Rect  # noqa: E402
from core.pet_spec import load_pet_spec  # noqa: E402
from core.pointer import PetPointer  # noqa: E402
from core.records import PetRecord  # noqa: E402
from core.toy import BallToy  # noqa: E402
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


def _make_view(seed=1, time_scale=1.0, animal="dog", record=None, pool=None):
    spec = load_pet_spec(ROOT / "assets" / "pets" / animal)
    sprites = SpriteBank(spec)
    sprites.load()
    body = create_pet(
        spec.movement, width=spec.frame_size[0], ground_offset=spec.ground_y, unit=1.0,
        physics=CFG.physics, behavior=CFG.walker, swimmer=CFG.swimmer,
        rng=random.Random(seed), below=spec.frame_size[1] - spec.ground_y,
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
    if record is None:
        record = PetRecord(id=1, animal=animal, name="테스트", fullness=CFG.needs.start,
                           mood=CFG.mood.start)
    if pool is None:
        pool = FoodPool(lifetime_s=60, max_items=10, gravity=CFG.physics.gravity,
                        max_fall=CFG.physics.max_fall_speed, sink_speed=14)
    view = PetView(
        record, body, spec, sprites, poller, CFG, pointer, pool, BallToy(CFG.toy, 1.0),
        dpr=1.0, status=lambda: (True, False), cursor=FakeCursor(),
    )
    view.spawn(500, 100)
    cfg_time = time_scale
    view._time_scale = cfg_time
    return view


def _run(view, seconds, start=0.0, active=True, hidden=False):
    t = start
    for _ in range(int(seconds * 60)):
        t += 1 / 60
        view.advance(t, active=active, hidden=hidden)
    return t


def test_dog_sprites_load_without_placeholders(qapp):
    spec = load_pet_spec(ROOT / "assets" / "pets" / "dog")
    bank = SpriteBank(spec)
    bank.load()
    assert bank.missing == []
    assert bank.frame("idle", 0).width() == 52
    assert bank.tomb().width() == 52


def test_missing_files_fall_back_to_placeholders(qapp, tmp_path):
    import json

    data = json.loads((ROOT / "assets" / "pets" / "dog" / "pet.json").read_text(encoding="utf-8"))
    from core.pet_spec import parse_pet_spec

    spec = parse_pet_spec("empty", data, tmp_path)
    bank = SpriteBank(spec)
    bank.load()
    assert set(bank.missing) == set(spec.actions) | {"tomb"}
    assert bank.frame("walk", 0).width() == 52


def test_view_falls_and_lands_on_floor(qapp):
    view = _make_view()
    _run(view, 4.0)
    assert view.body.feet_y == pytest.approx(760)
    assert view.body.is_grounded()


def test_view_mirrors_art_when_facing_left(qapp):
    view = _make_view()
    _run(view, 4.0)
    view.body.facing = -1
    _run(view, 0.1, start=4.0)
    assert view._art_key is not None and view._art_key[2] == -1


def test_advance_survives_empty_world(qapp):
    view = _make_view()
    view._poller.latest = build_snapshot([], [], CFG.physics.min_surface_width)
    _run(view, 1.0)
    assert view.body.feet_y == 100  # 모니터가 없으면 물리를 건너뛴다


def test_active_time_only_counts_when_active(qapp):
    view = _make_view()
    _run(view, 10.0, active=False)
    assert view.record.active_s == 0
    _run(view, 10.0, start=10.0, active=True)
    assert view.record.active_s == pytest.approx(10.0, abs=0.5)


def test_hidden_pauses_hunger_timer_only(qapp):
    view = _make_view()
    view.needs.fullness = 10.0  # 배고픔 구간
    _run(view, 5.0, hidden=True)
    assert view.needs.hunger_s == 0
    assert view.needs.fullness < 10.0  # 포만감은 계속 줄어든다
    _run(view, 5.0, start=5.0, hidden=False)
    assert view.needs.hunger_s > 0


def test_time_scale_speeds_up_needs_and_mood(qapp):
    slow = _make_view(time_scale=1.0)
    fast = _make_view(time_scale=4.0)
    _run(slow, 10.0)
    _run(fast, 10.0)
    assert fast.needs.fullness < slow.needs.fullness


def test_real_clock_jump_is_capped(qapp):
    view = _make_view()
    view.advance(0.0)
    view.advance(60.0)
    assert view.needs.fullness > CFG.needs.start - 1.0


def test_critical_notice_emitted_once(qapp):
    view = _make_view()
    notices = []
    view.noticed.connect(notices.append)
    view.needs.fullness = 0.0
    view.needs.hunger_s = view.needs.critical_s
    _run(view, 0.5)
    _run(view, 0.5, start=0.5)
    assert len([n for n in notices if "배고파" in n]) == 1


def test_growth_needs_both_hours_and_meals(qapp):
    view = _make_view()
    view.record.active_s = CFG.growth.hours[0] * 3600
    view.record.meals = 0
    _run(view, 0.2)
    assert view.stage == 1  # 시간만으로는 자라지 않는다
    view.record.meals = CFG.growth.meals[0]
    _run(view, 0.2, start=0.2)
    assert view.stage == 2
    assert view.record.stage == 2


def test_death_shows_die_then_tomb_and_freezes(qapp):
    view = _make_view()
    _run(view, 4.0)
    view.needs.hunger_s = view.needs.death_s
    view.needs.fullness = 0.0
    t = _run(view, 0.1, start=4.0)
    cx_before = view.body.cx
    assert view.dead
    assert view._art_key[0] == "die"
    t = _run(view, 4.0, start=t)
    assert view._art_key[0] == "tomb"
    assert view.body.cx == cx_before
    assert view.record.dead and view.record.died_at is not None


def test_death_is_not_reached_by_active_time_while_idle(qapp):
    view = _make_view()
    view.needs.fullness = 0.0
    _run(view, 20.0, active=False)  # 활성 사용이 아니면 배고픔 타이머도 돌지 않는다
    assert view.needs.hunger_s == 0
    assert not view.dead


def test_info_text_shows_active_time(qapp):
    view = _make_view()
    view.record.active_s = 3725
    assert "함께한 시간: 1시간 2분" in view.info_text()


def test_food_pool_is_shared_and_pet_eats_meal(qapp):
    pool = FoodPool(lifetime_s=60, max_items=10, gravity=1400, max_fall=900, sink_speed=14)
    view = _make_view(pool=pool)
    _run(view, 4.0)
    view.needs.fullness = 5.0
    pool.drop("food_bone", view.body.cx + 150, 760, 760)
    _run(view, 40.0, start=4.0)
    assert view.needs.fullness > 5.0
    assert view.record.meals >= 1
    assert pool.items == []


def test_food_expires_after_one_minute(qapp):
    pool = FoodPool(lifetime_s=60, max_items=10, gravity=1400, max_fall=900, sink_speed=14)
    pool.drop("food_bone", 900, 760, 760)
    for _ in range(59):
        pool.step(1.0)
    assert len(pool.items) == 1
    pool.step(1.5)
    assert pool.items == []
