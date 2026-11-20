"""PetView 통합 스모크 테스트 (오프스크린 Qt, 고정된 가짜 세계 사용)."""

import os
import random
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.config import load_config  # noqa: E402
from core.geometry import MonitorInfo, Rect  # noqa: E402
from core.pet_spec import load_pet_spec, parse_pet_spec  # noqa: E402
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


def _make_view(seed=1):
    spec = load_pet_spec(ROOT / "assets" / "pets" / "dog")
    sprites = SpriteBank(spec)
    sprites.load()
    body = create_pet(
        "walker", width=64, ground_offset=56, unit=1.0,
        physics=CFG.physics, behavior=CFG.walker, rng=random.Random(seed),
    )
    poller = WorldPoller(CFG.physics.window_poll_hz, CFG.physics.min_surface_width)
    mon = MonitorInfo(rect=Rect(0, 0, 1000, 800), work=Rect(0, 0, 1000, 760))
    poller.latest = build_snapshot([], [mon], CFG.physics.min_surface_width)
    view = PetView(body, spec, sprites, poller, pet_scale=1, fps=60)
    view.spawn(500, 100)
    return view


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
    assert bank.frame("idle", 0).width() == 64
    assert bank.tomb().width() == 64


def test_missing_files_fall_back_to_placeholders(qapp, tmp_path, monkeypatch):
    import json

    data = json.loads((ROOT / "assets" / "pets" / "dog" / "pet.json").read_text(encoding="utf-8"))
    spec = parse_pet_spec("empty", data, tmp_path)  # 그림 파일이 하나도 없다
    bank = SpriteBank(spec)
    bank.load()
    assert set(bank.missing) == set(spec.actions) | {"tomb"}
    assert bank.frame("walk", 0).width() == 64


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
    key_before = view._art_key
    _run(view, 0.5, start=t)
    assert key_before == ("sit", 0, 1)
    assert view._art_key == key_before


def test_advance_survives_empty_world(qapp):
    view = _make_view()
    view._poller.latest = build_snapshot([], [], CFG.physics.min_surface_width)
    _run(view, 1.0)  # 모니터가 없으면 물리 갱신을 건너뛰고 죽지 않는다
    assert view._body.feet_y == 100  # 낙하하지 않고 그대로 있다
