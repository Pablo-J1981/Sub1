"""기분 수치 테스트 (Qt 비의존)."""

from pathlib import Path

from core.config import load_config
from core.mood import NEUTRAL, Mood

CFG = load_config(Path(__file__).resolve().parents[1] / "config" / "settings.json")


def make_mood(**overrides):
    from dataclasses import replace
    return Mood(replace(CFG.mood, **overrides) if overrides else CFG.mood)


def test_starts_at_configured_value():
    assert make_mood().value == CFG.mood.start


def test_petting_raises_mood_and_starts_joy():
    m = make_mood(start=50, pet_gain=5, pet_joy_duration_s=2.0)
    joy = m.petted()
    assert m.value == 55
    assert joy == 2.0
    assert m.is_joyful


def test_joy_expires_over_time():
    m = make_mood(start=50, pet_joy_duration_s=1.0)
    m.petted()
    m.step(0.5)
    assert m.is_joyful
    m.step(0.6)
    assert not m.is_joyful


def test_mood_drifts_back_to_neutral_and_stops_there():
    m = make_mood(start=90, decay_per_s=10)
    m.step(1.0)
    assert m.value == 80
    m.step(100.0)
    assert m.value == NEUTRAL
    low = make_mood(start=10, decay_per_s=10)
    low.step(100.0)
    assert low.value == NEUTRAL


def test_drop_penalty_and_bounds():
    m = make_mood(start=2, drop_penalty=5)
    m.dropped()
    assert m.value == 0
    m2 = make_mood(start=99, pet_gain=10)
    m2.petted()
    assert m2.value == 100


def test_sad_and_labels():
    m = make_mood(start=10, sad_below=20)
    assert m.is_sad
    assert m.label() == "나쁨"
    m.value = 80
    assert m.label() == "좋음"
    m.value = 50
    assert m.label() == "보통"
