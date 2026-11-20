"""펫 에셋 규격 검사: pet.json 필수 항목, 동작 누락, 그림 파일 존재 여부."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PETS = ROOT / "assets" / "pets"

REQUIRED_COMMON = {"hungry", "sick", "die"}
REQUIRED_BY_MOVEMENT = {
    "walker": {"idle", "walk", "sit", "sleep", "fall", "land", "scared",
               "jump", "eat", "held", "happy", "sad"},
    "swimmer": {"idle", "swim", "startled", "eat", "held", "happy", "sad"},
}


def _pet_dirs() -> list[Path]:
    return sorted(p for p in PETS.iterdir() if (p / "pet.json").exists())


@pytest.mark.parametrize("pet_dir", _pet_dirs(), ids=lambda p: p.name)
def test_pet_json_has_required_actions(pet_dir: Path):
    spec = json.loads((pet_dir / "pet.json").read_text(encoding="utf-8"))
    movement = spec["movement"]
    assert movement in REQUIRED_BY_MOVEMENT

    required = REQUIRED_BY_MOVEMENT[movement] | REQUIRED_COMMON
    missing = required - set(spec["actions"])
    assert not missing, f"{pet_dir.name} 누락 동작: {sorted(missing)}"


@pytest.mark.parametrize("pet_dir", _pet_dirs(), ids=lambda p: p.name)
def test_pet_action_files_exist(pet_dir: Path):
    spec = json.loads((pet_dir / "pet.json").read_text(encoding="utf-8"))
    for name, action in spec["actions"].items():
        path = pet_dir / action["file"]
        assert path.exists(), f"{pet_dir.name}/{name}: 파일 없음 {path}"
        assert action["frames"] >= 1 and action["fps"] > 0
    assert (pet_dir / spec["tomb"]).exists()


@pytest.mark.parametrize("pet_dir", _pet_dirs(), ids=lambda p: p.name)
def test_pet_images_match_declared_frame_size(pet_dir: Path):
    from PIL import Image

    spec = json.loads((pet_dir / "pet.json").read_text(encoding="utf-8"))
    frame_w, frame_h = spec["frame_size"]
    for name, action in spec["actions"].items():
        with Image.open(pet_dir / action["file"]) as img:
            assert img.mode == "RGBA", f"{name} 은(는) 투명 채널이 있어야 합니다"
            assert img.size == (frame_w * action["frames"], frame_h), f"{name} 크기 불일치"
