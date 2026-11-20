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
    assert cfg.display.pet_scale == 4
    assert cfg.debug.placeholder_frame_size == (32, 32)
    assert cfg.physics.gravity == 1400
    assert cfg.walker.jump_off_chance == 0.15
    assert sum(cfg.walker.action_weights.values()) > 0


def test_shipped_settings_file_is_valid():
    cfg = load_config(ROOT / "config" / "settings.json")
    assert cfg.version == 1


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
