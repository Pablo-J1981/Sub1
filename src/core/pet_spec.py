"""동물 설정(pet.json) 로딩과 검증 (Qt 비의존).

새 동물 추가 = assets/pets/<동물>/ 폴더에 pet.json과 그림을 넣는 것.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_COMMON = frozenset({"hungry", "sick", "die"})
REQUIRED_BY_MOVEMENT: dict[str, frozenset[str]] = {
    "walker": frozenset({
        "idle", "walk", "sit", "sleep", "fall", "land", "scared",
        "jump", "eat", "held", "happy", "sad",
    }),
    "swimmer": frozenset({
        "idle", "swim", "startled", "eat", "held", "happy", "sad",
    }),
}


class PetSpecError(ValueError):
    """pet.json 내용이 규격에 맞지 않을 때 발생한다."""


@dataclass(frozen=True)
class ActionSpec:
    file: str    # pet 폴더 기준 상대 경로 (가로로 프레임을 이어 붙인 시트)
    frames: int
    fps: float


@dataclass(frozen=True)
class PetSpec:
    key: str                              # 폴더 이름 (예: "dog")
    name_ko: str
    movement: str                         # "walker" 또는 "swimmer"
    frame_size: tuple[int, int]           # 한 프레임 크기 (원본 픽셀)
    ground_y: int                         # 그림 안에서 발이 닿는 y (원본 픽셀)
    actions: dict[str, ActionSpec]
    tomb: str
    root: Path                            # pet 폴더 경로


def _positive_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PetSpecError(f"{what} 은(는) 양의 정수여야 합니다.")
    return value


def parse_pet_spec(key: str, data: dict, root: Path) -> PetSpec:
    if not isinstance(data, dict):
        raise PetSpecError("pet.json 최상위 값은 객체여야 합니다.")

    movement = data.get("movement")
    if movement not in REQUIRED_BY_MOVEMENT:
        raise PetSpecError(f"알 수 없는 이동 타입: {movement!r}")

    frame = data.get("frame_size")
    if not isinstance(frame, list) or len(frame) != 2:
        raise PetSpecError("frame_size 는 [w, h] 여야 합니다.")
    frame_w = _positive_int(frame[0], "frame_size[0]")
    frame_h = _positive_int(frame[1], "frame_size[1]")

    ground_y = data.get("ground_y")
    if isinstance(ground_y, bool) or not isinstance(ground_y, int) or not 1 <= ground_y <= frame_h:
        raise PetSpecError(f"ground_y 는 1 이상 {frame_h} 이하의 정수여야 합니다.")

    raw_actions = data.get("actions")
    if not isinstance(raw_actions, dict):
        raise PetSpecError("actions 는 객체여야 합니다.")

    required = REQUIRED_BY_MOVEMENT[movement] | REQUIRED_COMMON
    missing = required - set(raw_actions)
    if missing:
        raise PetSpecError(f"누락된 동작: {sorted(missing)}")

    actions: dict[str, ActionSpec] = {}
    for name, spec in raw_actions.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("file"), str):
            raise PetSpecError(f"동작 '{name}' 의 file 이 없습니다.")
        frames = _positive_int(spec.get("frames"), f"{name}.frames")
        fps = spec.get("fps")
        if isinstance(fps, bool) or not isinstance(fps, (int, float)) or fps <= 0:
            raise PetSpecError(f"{name}.fps 는 0보다 큰 숫자여야 합니다.")
        actions[name] = ActionSpec(file=spec["file"], frames=frames, fps=float(fps))

    tomb = data.get("tomb")
    if not isinstance(tomb, str):
        raise PetSpecError("tomb 은 파일 이름 문자열이어야 합니다.")

    name_ko = data.get("name_ko", key)
    if not isinstance(name_ko, str):
        raise PetSpecError("name_ko 는 문자열이어야 합니다.")

    return PetSpec(
        key=key,
        name_ko=name_ko,
        movement=movement,
        frame_size=(frame_w, frame_h),
        ground_y=ground_y,
        actions=actions,
        tomb=tomb,
        root=root,
    )


def load_pet_spec(root: Path) -> PetSpec:
    """assets/pets/<동물> 폴더에서 pet.json을 읽는다."""
    root = Path(root)
    path = root / "pet.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PetSpecError(f"pet.json 을 읽을 수 없습니다: {path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise PetSpecError(f"pet.json JSON 형식 오류: {path} ({exc})") from exc
    return parse_pet_spec(root.name, data, root)
