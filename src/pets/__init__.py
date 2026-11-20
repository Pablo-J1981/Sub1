"""동물 이동 타입 모음. 새 이동 타입은 여기에 클래스를 추가하고 create_pet에 등록한다."""

from __future__ import annotations

import random

from core.config import PhysicsConfig, WalkerConfig
from pets.base import PetBody
from pets.walker import WalkerPet


def create_pet(
    movement: str,
    *,
    width: float,
    ground_offset: float,
    unit: float,
    physics: PhysicsConfig,
    behavior: WalkerConfig,
    rng: random.Random,
) -> PetBody:
    if movement == "walker":
        return WalkerPet(
            width=width,
            ground_offset=ground_offset,
            unit=unit,
            physics=physics,
            behavior=behavior,
            rng=rng,
        )
    if movement == "swimmer":
        raise NotImplementedError("헤엄 타입은 6단계에서 구현됩니다.")
    raise ValueError(f"알 수 없는 이동 타입: {movement!r}")
