import json
from pathlib import Path

import pytest

from core.config import ConfigError, load_config, parse_config

ROOT = Path(__file__).resolve().parents[1]


def _valid() -> dict:
    return json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))


def test_parse_valid_config():
    cfg = parse_config(_valid())
    assert cfg.display.animation_fps == 60.0
    assert cfg.display.pet_scale == 2
    assert cfg.debug.placeholder_frame_size == (32, 32)
    assert cfg.physics.gravity == 1400
    assert cfg.walker.jump_off_chance == 0.15
    assert sum(cfg.walker.action_weights.values()) > 0


def test_shipped_settings_file_is_valid():
    cfg = load_config(ROOT / "config" / "settings.json")
    assert cfg.version == 1
    assert cfg.food.lifetime_s == 60
    assert cfg.needs.decay_per_hour == 20
    assert cfg.growth.hours == (5, 20, 50, 100)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(version=2),
        lambda d: d["display"].update(pet_scale=0),
        lambda d: d["display"].update(pet_scale=True),  # bool 은 정수로 받지 않는다
        lambda d: d["display"].update(animation_fps="60"),
        lambda d: d["debug"].update(placeholder_frame_size=[32]),
        lambda d: d["debug"].update(placeholder_frame_size=[0, 32]),
        lambda d: d.pop("display"),
        lambda d: d.pop("physics"),
        lambda d: d["physics"].update(gravity=0),
        lambda d: d["walker"].update(jump_off_chance=1.5),
        lambda d: d["walker"].update(idle_duration_s=[5, 1]),  # 최소 > 최대
        lambda d: d["walker"]["action_weights"].update(idle=-1),
        lambda d: d["walker"].update(action_weights={"idle": 1}),
        lambda d: d["pointer"].update(throw_inertia=-1),
        lambda d: d["pointer"].update(velocity_window_s=0),
        lambda d: d["mood"].update(start=101),
        lambda d: d["debug"].update(time_scale=0),
        lambda d: d["debug"].update(time_scale=21),
        lambda d: d["needs"].update(hungry_below=-1),
        lambda d: d.pop("mood"),
        lambda d: d["needs"].update(critical_hours=9),  # 위독은 사망 시간보다 빨라야 한다
        lambda d: d["growth"].update(hours=[5, 1, 50, 100]),  # 작은 값부터 순서대로
        lambda d: d["growth"].update(meals=[5, 20, 50]),  # 길이 4 필요
        lambda d: d["growth"].update(pixel_scale=[0, 2, 3, 3, 4]),
        lambda d: d["food"].update(lifetime_s=0),
        lambda d: d["toy"].update(play_s=-1),
        lambda d: d["activity"].update(idle_pause_s=0),
        lambda d: d.pop("swimmer"),
    ],
)
def test_invalid_config_raises(mutate):
    data = _valid()
    mutate(data)
    with pytest.raises(ConfigError):
        parse_config(data)


def test_load_config_reports_broken_json(tmp_path: Path):
    bad = tmp_path / "settings.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(bad)
