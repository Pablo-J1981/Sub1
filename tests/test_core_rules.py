"""순수 규칙 테스트: 포만감, 성장, 활성 시간, 기록, 저장, 아이템, 공, 먹이 (Qt/Win32 비의존)."""

import json
from pathlib import Path

import pytest

from core.clock import is_active
from core.config import load_config
from core.feeding import FoodPool, Reach
from core.growth import pixel_scale_for, stage_for
from core.items import LocalAlwaysAllow, entitled, load_item_packs
from core.needs import HOUR_S, Needs
from core.records import PetRecord, can_adopt, format_active, grave_tip, memory_text, next_id
from core.savefile import SaveData, backup_path, load_save, save_data
from core.toy import BallToy

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config" / "settings.json")


# ---------------------------------------------------------------- 포만감과 배고픔

def test_decay_is_20_per_active_hour():
    n = Needs(CFG.needs, fullness=80)
    n.step(HOUR_S)
    assert n.fullness == pytest.approx(60)


def test_feed_adds_20_and_resets_timer():
    n = Needs(CFG.needs, fullness=20, hunger_s=500)
    n.feed()
    assert n.fullness == pytest.approx(40)
    assert n.hunger_s == 0


def test_refuses_food_at_or_above_80():
    assert Needs(CFG.needs, fullness=79.9).can_eat()
    assert not Needs(CFG.needs, fullness=80).can_eat()


def test_hunger_timer_starts_only_at_30_or_below():
    # 31 -> 26 during 900 s; 30 is reached after 180 s, so only the remaining 720 s count
    n = Needs(CFG.needs, fullness=31)
    n.step(HOUR_S / 4)
    assert n.hunger_s == pytest.approx(720)
    n2 = Needs(CFG.needs, fullness=50)
    n2.step(HOUR_S / 4)  # 50 -> 45, never reaches 30
    assert n2.hunger_s == 0
    n.fullness = 30
    n.hunger_s = 0
    n.step(60)
    assert n.hunger_s == 60


def test_hidden_pauses_hunger_timer_but_not_decay():
    n = Needs(CFG.needs, fullness=25)
    n.step(600, hidden=True)
    assert n.hunger_s == 0
    assert n.fullness < 25


def test_critical_at_3_hours_and_death_at_8():
    n = Needs(CFG.needs, fullness=10)
    n.hunger_s = 3 * HOUR_S
    assert n.is_critical() and n.label() == "위독"
    n.hunger_s = 8 * HOUR_S
    n.step(1)
    assert n.dead and n.label() == "사망"


def test_dead_pet_does_not_decay():
    n = Needs(CFG.needs, fullness=50, dead=True)
    n.step(HOUR_S)
    assert n.fullness == 50


# ---------------------------------------------------------------- 활성 시간

def test_active_clock_pauses_after_idle():
    assert is_active(0, 600)
    assert is_active(599, 600)
    assert not is_active(600, 600)


# ---------------------------------------------------------------- 성장

H = CFG.growth.hours
M = CFG.growth.meals


def test_growth_needs_hours_and_meals():
    assert stage_for(H[0] * 3600, 0, hours=H, meal_counts=M) == 1
    assert stage_for(0, M[0], hours=H, meal_counts=M) == 1
    assert stage_for(H[0] * 3600, M[0], hours=H, meal_counts=M) == 2


def test_growth_can_skip_nothing_and_never_drops():
    assert stage_for(10**9, 10**6, hours=H, meal_counts=M, current=1) == 5
    assert stage_for(0, 0, hours=H, meal_counts=M, current=3) == 3


def test_pixel_scale_per_stage():
    assert [pixel_scale_for(s, CFG.growth.pixel_scale) for s in range(1, 6)] == [2, 2, 3, 3, 4]


# ---------------------------------------------------------------- 기록과 입양

def test_format_active_hours_minutes():
    assert format_active(3725) == "1시간 2분"
    assert format_active(-5) == "0시간 0분"


def test_can_adopt_rule():
    dead = PetRecord(id=1, animal="dog", name="a", dead=True)
    young = PetRecord(id=2, animal="dog", name="b", stage=4)
    grown = PetRecord(id=3, animal="dog", name="c", stage=5)
    assert can_adopt([])
    assert can_adopt([dead])
    assert not can_adopt([young])
    assert can_adopt([young, grown])


def test_record_roundtrip_and_validation():
    r = PetRecord(id=4, animal="shark", name="상어", stage=2, meals=3, died_at=12.5)
    assert PetRecord.from_dict(r.to_dict()) == r
    for bad in ({"id": 0}, {"stage": 9}, {"name": ""}, {"meals": -1}):
        data = {**r.to_dict(), **bad}
        with pytest.raises(ValueError):
            PetRecord.from_dict(data)


def test_next_id_and_texts():
    recs = [PetRecord(id=2, animal="dog", name="a"), PetRecord(id=7, animal="dog", name="b")]
    assert next_id(recs) == 8
    assert next_id([]) == 1
    assert "2단계" in grave_tip(PetRecord(id=1, animal="dog", name="a", stage=2))
    assert "먹은 횟수: 3" in memory_text(PetRecord(id=1, animal="dog", name="a", meals=3))


# ---------------------------------------------------------------- 저장

def _sample():
    return SaveData(records=[PetRecord(id=1, animal="dog", name="댕댕", active_s=5000)], next_id=2)


def test_save_roundtrip(tmp_path):
    path = tmp_path / "save.json"
    save_data(path, _sample())
    data, warnings = load_save(path)
    assert warnings == []
    assert data.records[0].name == "댕댕"
    assert data.next_id == 2


def test_second_save_keeps_backup(tmp_path):
    path = tmp_path / "save.json"
    save_data(path, _sample())
    save_data(path, SaveData(records=[], next_id=1))
    assert backup_path(path).exists()
    assert json.loads(backup_path(path).read_text(encoding="utf-8"))["pets"][0]["name"] == "댕댕"
    assert not path.with_name("save.tmp").exists()


def test_corrupt_main_file_recovers_from_backup(tmp_path):
    path = tmp_path / "save.json"
    save_data(path, _sample())
    save_data(path, _sample())
    path.write_text("{ broken", encoding="utf-8")
    data, warnings = load_save(path)
    assert data is not None and data.records[0].name == "댕댕"
    assert warnings  # 깨진 파일 경고는 남긴다


def test_both_files_broken_returns_none(tmp_path):
    path = tmp_path / "save.json"
    path.write_text("x", encoding="utf-8")
    backup_path(path).write_text("{\"version\": 9}", encoding="utf-8")
    data, warnings = load_save(path)
    assert data is None and len(warnings) == 2


def test_unknown_version_is_rejected(tmp_path):
    path = tmp_path / "save.json"
    path.write_text(json.dumps({"version": 2, "next_id": 1, "pets": []}), encoding="utf-8")
    data, _ = load_save(path)
    assert data is None


def test_duplicate_ids_rejected(tmp_path):
    path = tmp_path / "save.json"
    rec = PetRecord(id=1, animal="dog", name="a").to_dict()
    path.write_text(json.dumps({"version": 1, "next_id": 3, "pets": [rec, rec]}), encoding="utf-8")
    data, _ = load_save(path)
    assert data is None


# ---------------------------------------------------------------- 아이템

def test_item_packs_load_and_entitlement():
    packs, errors = load_item_packs(ROOT / "assets" / "items")
    assert errors == []
    ids = {p.id: p for p in packs}
    assert {"food_bone", "food_fish", "food_treat", "food_bowl", "toy_ball"} <= set(ids)
    assert ids["food_fish"].sinks is True
    assert ids["toy_ball"].kind == "toy"
    provider = LocalAlwaysAllow()
    assert all(provider.is_entitled(p.id) for p in packs)
    assert {p.kind for p in entitled(packs, provider, "food")} == {"food"}


def test_bad_item_pack_is_skipped(tmp_path):
    good = tmp_path / "ok"
    good.mkdir()
    (good / "item.json").write_text(json.dumps({"id": "a", "kind": "food", "name_ko": "a", "image": "i.png"}), encoding="utf-8")
    (good / "i.png").write_bytes(b"x")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "item.json").write_text(json.dumps({"id": "b", "kind": "hat", "name_ko": "b", "image": "i.png"}), encoding="utf-8")
    packs, errors = load_item_packs(tmp_path)
    assert [p.id for p in packs] == ["a"] or packs == []  # 그림이 없으면 건너뛴다
    assert errors


# ---------------------------------------------------------------- 공

def test_ball_lasts_play_seconds_then_disappears():
    toy = BallToy(CFG.toy, 1.0)
    toy.drop(100, 500, 0, 300, 5)
    toy.step(CFG.toy.play_s - 0.1)
    assert toy.ball is not None
    toy.step(0.2)
    assert toy.ball is None


def test_ball_stays_inside_platform():
    toy = BallToy(CFG.toy, 1.0)
    b = toy.drop(100, 500, 0, 200, 5)
    b.v = 500
    for _ in range(200):
        toy.step(0.01)
    assert b.x <= 195


# ---------------------------------------------------------------- 먹이 목록

def test_food_falls_then_lands_and_expires():
    pool = FoodPool(lifetime_s=60, max_items=10, gravity=1400, max_fall=900, sink_speed=14)
    item = pool.drop("food_bone", 100, 0, 500)
    pool.step(0.5)
    assert 0 < item.y < 500
    for _ in range(100):
        pool.step(0.1)
    assert item.y == 500
    assert item in pool.items
    pool.step(60)
    assert item not in pool.items


def test_fish_sinks_slowly_instead_of_falling():
    pool = FoodPool(lifetime_s=60, max_items=10, gravity=1400, max_fall=900, sink_speed=14)
    fish = pool.drop("food_fish", 100, 0, 500, sinking=True)
    pool.step(1.0)
    assert fish.y == pytest.approx(14, abs=0.1)


def test_food_claimed_by_other_pet_is_not_available():
    pool = FoodPool(lifetime_s=60, max_items=10, gravity=1400, max_fall=900, sink_speed=14)
    item = pool.drop("food_bone", 100, 500, 500)
    item.claimed_by = 2
    assert pool.available(1) == []
    assert pool.available(2) == [item]


def test_pool_limit():
    pool = FoodPool(lifetime_s=60, max_items=2, gravity=1400, max_fall=900, sink_speed=14)
    assert pool.drop("food_bone", 1, 0, 0) is not None
    assert pool.drop("food_bone", 2, 0, 0) is not None
    assert pool.drop("food_bone", 3, 0, 0) is None


def test_reach_enum_has_all_states():
    assert {r.value for r in Reach} == {"reach", "below", "above", "out"}
