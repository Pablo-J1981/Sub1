"""펫 기록 한 줄 (Qt/Win32 비의존). 저장 파일의 펫 한 마리에 해당한다.

active_s 는 활성 사용 시간(초) = '함께한 시간'이다.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

MAX_NAME_LEN = 12
ADOPT_STAGE = 5


@dataclass
class PetRecord:
    id: int
    animal: str
    name: str
    stage: int = 1
    active_s: float = 0.0
    meals: int = 0
    fullness: float = 70.0
    hunger_s: float = 0.0
    mood: float = 60.0
    dead: bool = False
    grave_cx: float | None = None
    grave_feet_y: float | None = None
    died_at: float | None = None  # 사망 시각 (유닉스 시간, 초)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PetRecord":
        if not isinstance(data, dict):
            raise ValueError("펫 기록이 객체가 아닙니다.")

        def num(key: str, lo: float, hi: float) -> float:
            v = data.get(key)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                raise ValueError(f"펫 기록 '{key}' 값이 잘못되었습니다: {v!r}")
            return float(v)

        animal = data.get("animal")
        name = data.get("name")
        if not isinstance(animal, str) or not animal:
            raise ValueError("펫 기록 'animal' 이 없습니다.")
        if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME_LEN:
            raise ValueError("펫 기록 'name' 이 잘못되었습니다.")
        pid = data.get("id")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
            raise ValueError("펫 기록 'id' 가 잘못되었습니다.")
        meals = data.get("meals")
        if isinstance(meals, bool) or not isinstance(meals, int) or meals < 0:
            raise ValueError("펫 기록 'meals' 가 잘못되었습니다.")
        stage = data.get("stage")
        if isinstance(stage, bool) or not isinstance(stage, int) or not 1 <= stage <= 5:
            raise ValueError("펫 기록 'stage' 가 잘못되었습니다.")
        dead = data.get("dead")
        if not isinstance(dead, bool):
            raise ValueError("펫 기록 'dead' 가 잘못되었습니다.")
        grave_cx = data.get("grave_cx")
        grave_y = data.get("grave_feet_y")
        if grave_cx is not None and not isinstance(grave_cx, (int, float)):
            raise ValueError("펫 기록 'grave_cx' 가 잘못되었습니다.")
        if grave_y is not None and not isinstance(grave_y, (int, float)):
            raise ValueError("펫 기록 'grave_feet_y' 가 잘못되었습니다.")
        return cls(
            id=pid,
            animal=animal,
            name=name.strip(),
            stage=stage,
            active_s=num("active_s", 0, 1e12),
            meals=meals,
            fullness=num("fullness", 0, 100),
            hunger_s=num("hunger_s", 0, 1e12),
            mood=num("mood", 0, 100),
            dead=dead,
            grave_cx=None if grave_cx is None else float(grave_cx),
            grave_feet_y=None if grave_y is None else float(grave_y),
            died_at=_opt_num(data.get("died_at")),
        )


def _opt_num(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("펫 기록 'died_at' 이 잘못되었습니다.")
    return float(value)


def living(records: list[PetRecord]) -> list[PetRecord]:
    return [r for r in records if not r.dead]


def can_adopt(records: list[PetRecord]) -> bool:
    """입양 조건: 살아 있는 펫이 없거나, 살아 있는 펫 중 5단계가 있을 때."""
    alive = living(records)
    return not alive or any(r.stage >= ADOPT_STAGE for r in alive)


def next_id(records: list[PetRecord], floor: int = 1) -> int:
    return max([floor] + [r.id + 1 for r in records])


def format_active(active_s: float) -> str:
    """함께한 시간 표시: 'N시간 M분'."""
    minutes = int(max(0.0, active_s) // 60)
    return f"{minutes // 60}시간 {minutes % 60}분"


def grave_tip(r: PetRecord) -> str:
    """무덤에 마우스를 올렸을 때: 이름, 단계, 함께한 시간."""
    return f"{r.name}\n{r.stage}단계 · 함께한 시간 {format_active(r.active_s)}"


def memory_text(r: PetRecord) -> str:
    """추억 보기 내용 (죽은 펫)."""
    lines = [
        f"이름: {r.name}",
        f"단계: {r.stage} / 5",
        f"함께한 시간: {format_active(r.active_s)}",
        f"먹은 횟수: {r.meals}",
    ]
    if r.died_at is not None:
        lines.append("떠난 날: " + time.strftime("%Y-%m-%d %H:%M", time.localtime(r.died_at)))
    return "\n".join(lines)
