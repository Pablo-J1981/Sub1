import copy
from pathlib import Path

import pytest

from core.pet_spec import PetSpecError, load_pet_spec, parse_pet_spec
from core.animation import frame_index

ROOT = Path(__file__).resolve().parents[1]


def _base(movement="walker"):
    actions = {n: {"file": f"stage1/{n}.png", "frames": 1, "fps": 2}
               for n in ["idle", "walk", "sit", "sleep", "fall", "land", "scared",
                         "jump", "eat", "held", "happy", "sad", "hungry", "sick", "die"]}
    if movement == "swimmer":
        actions = {n: {"file": f"stage1/{n}.png", "frames": 1, "fps": 2}
                   for n in ["idle", "swim", "startled", "eat", "held", "happy",
                             "sad", "hungry", "sick", "die"]}
    return {"movement": movement, "frame_size": [64, 64], "ground_y": 56,
            "actions": actions, "tomb": "tomb.png"}


def test_shipped_dog_and_shark_load():
    dog = load_pet_spec(ROOT / "assets" / "pets" / "dog")
    shark = load_pet_spec(ROOT / "assets" / "pets" / "shark")
    assert dog.movement == "walker" and dog.ground_y == 56
    assert shark.movement == "swimmer"


def test_missing_required_action_is_rejected():
    data = _base()
    del data["actions"]["fall"]
    with pytest.raises(PetSpecError, match="fall"):
        parse_pet_spec("x", data, Path("."))


def test_swimmer_does_not_need_walker_actions():
    spec = parse_pet_spec("x", _base("swimmer"), Path("."))
    assert "walk" not in spec.actions


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(movement="flyer"),
        lambda d: d.update(ground_y=0),
        lambda d: d.update(ground_y=65),
        lambda d: d.update(frame_size=[64]),
        lambda d: d["actions"]["idle"].update(frames=0),
        lambda d: d["actions"]["idle"].update(fps=0),
    ],
)
def test_invalid_pet_spec(mutate):
    data = copy.deepcopy(_base())
    mutate(data)
    with pytest.raises(PetSpecError):
        parse_pet_spec("x", data, Path("."))


def test_load_reports_broken_json(tmp_path):
    (tmp_path / "pet.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(PetSpecError):
        load_pet_spec(tmp_path)


def test_frame_index_cycles():
    assert frame_index(0, 4, 10) == 0
    assert frame_index(0.1, 4, 10) == 1
    assert frame_index(0.45, 4, 10) == 0  # 4프레임 뒤 처음으로
    assert frame_index(5, 1, 10) == 0
