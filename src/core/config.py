"""설정 파일(config/settings.json) 로딩과 검증. Qt/Win32 비의존.

모든 수치는 설정 파일에 있고, 여기서는 타입과 범위만 검증한다.
물리/행동 수치 단위: 별도 표기가 없으면 "원본 픽셀"(스프라이트 한 칸 기준)이다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_CONFIG_VERSION = 1
ACTION_WEIGHT_KEYS = ("idle", "walk", "sit", "sleep")


class ConfigError(ValueError):
    """설정 파일 내용이 잘못되었을 때 발생한다."""


@dataclass(frozen=True)
class DisplayConfig:
    animation_fps: float
    pet_scale: int  # 먹이, 공, 무덤 등 물건 그림의 정수 배율 (펫 크기는 growth.pixel_scale)


@dataclass(frozen=True)
class DebugConfig:
    placeholder_frame_size: tuple[int, int]
    start_pet: str  # 처음 펫이 없을 때 쓸 기본 동물 (첫 실행 창의 기본 선택)
    time_scale: float  # 시간 배속. 펫 안의 시간(성장, 포만감, 움직임)에만 적용


@dataclass(frozen=True)
class PhysicsConfig:
    gravity: float
    max_fall_speed: float
    landing_duration_s: float
    min_surface_width: float
    support_tolerance: float
    window_poll_hz: float
    spawn_height: float
    max_step_s: float


@dataclass(frozen=True)
class WalkerConfig:
    walk_speed: float
    jump_up_speed: float
    jump_off_speed: float
    jump_off_chance: float
    edge_margin: float
    scared_duration_s: tuple[float, float]
    startled_duration_s: float
    idle_duration_s: tuple[float, float]
    walk_duration_s: tuple[float, float]
    sit_duration_s: tuple[float, float]
    sleep_duration_s: tuple[float, float]
    action_weights: dict[str, float]


@dataclass(frozen=True)
class SwimmerConfig:
    swim_speed: float            # 원본 px/s
    turn_s: float                # 방향을 바꾸는 데 걸리는 시간(초)
    retarget_s: tuple[float, float]
    sink_speed: float            # 원본 px/s. 죽은 뒤 가라앉는 속도
    startle_radius: float        # 원본 px. 빠른 커서가 이 안으로 들어오면 놀란다
    startle_cursor_speed: float  # 원본 px/s. 이보다 빠른 커서에만 놀란다
    startle_speed: float         # 원본 px/s. 놀라서 달아나는 속도
    startle_duration_s: float


@dataclass(frozen=True)
class PointerConfig:
    drag_threshold_px: float
    min_stroke_px: float
    throw_inertia: float
    max_throw_speed: float
    velocity_window_s: float


@dataclass(frozen=True)
class MoodConfig:
    start: float
    pet_gain: float
    pet_joy_duration_s: float
    drop_penalty: float
    decay_per_s: float
    sad_below: float


@dataclass(frozen=True)
class NeedsConfig:
    start: float            # 처음 포만감 (0~100)
    decay_per_hour: float   # 활성 사용 1시간에 줄어드는 포만감
    hungry_below: float     # 이 값 이하가 되면 배고픔 타이머가 돈다
    critical_hours: float   # 배고픔 타이머가 이 시간이면 위독
    death_hours: float      # 배고픔 타이머가 이 시간이면 사망
    food_amount: float      # 한 끼에 차는 포만감
    eat_refuse_at: float    # 포만감이 이 값 이상이면 먹지 않는다
    eat_duration_s: float   # 먹는 데 걸리는 시간(초)


@dataclass(frozen=True)
class GrowthConfig:
    hours: tuple[float, ...]    # 1→2, 2→3, 3→4, 4→5 단계로 넘어가는 활성 시간(시간 단위)
    meals: tuple[int, ...]      # 같은 단계에서 필요한 누적 먹은 횟수 (시간과 함께 둘 다 채워야 한다)
    pixel_scale: tuple[int, ...]  # 단계별 정수 배율 (1~5단계)


@dataclass(frozen=True)
class ActivityConfig:
    idle_pause_s: float  # 마지막 입력 후 이 시간이 지나면 활성 사용 시간이 멈춘다
    autosave_s: float    # 자동 저장 간격


@dataclass(frozen=True)
class FoodConfig:
    lifetime_s: float  # 먹이가 놓인 뒤 이 시간이 지나면 사라진다 (실제 시간)
    max_items: int     # 동시에 놓을 수 있는 먹이 개수


@dataclass(frozen=True)
class ToyConfig:
    play_s: float      # 공이 머무는 시간 (실제 시간)
    push_speed: float  # 원본 px/s. 펫이 밀 때 공이 굴러가는 속도
    friction: float    # 원본 px/s^2. 밀린 뒤 공이 멈추는 감속


@dataclass(frozen=True)
class AppConfig:
    version: int
    display: DisplayConfig
    debug: DebugConfig
    physics: PhysicsConfig
    walker: WalkerConfig
    swimmer: SwimmerConfig
    pointer: PointerConfig
    mood: MoodConfig
    needs: NeedsConfig
    growth: GrowthConfig
    activity: ActivityConfig
    food: FoodConfig
    toy: ToyConfig


def _require_dict(data: Any, key: str) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"설정 항목 '{key}' 이(가) 객체(dict)가 아닙니다.")
    return value


def _require_number(section: dict, key: str, lo: float, hi: float) -> float:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"'{key}' 은(는) 숫자여야 합니다.")
    if not lo <= value <= hi:
        raise ConfigError(f"'{key}' 은(는) {lo} 이상 {hi} 이하여야 합니다. (현재: {value})")
    return float(value)


def _require_int(section: dict, key: str, lo: int, hi: int) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"'{key}' 은(는) 정수여야 합니다.")
    if not lo <= value <= hi:
        raise ConfigError(f"'{key}' 은(는) {lo} 이상 {hi} 이하여야 합니다. (현재: {value})")
    return value


def _require_str(section: dict, key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{key}' 은(는) 비어 있지 않은 문자열이어야 합니다.")
    return value


def _require_pair(section: dict, key: str, lo: float, hi: float) -> tuple[float, float]:
    """[최소, 최대] 형식의 범위. 최소가 최대보다 크면 오류."""
    value = section.get(key)
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)
    ):
        raise ConfigError(f"'{key}' 은(는) 숫자 두 개 [최소, 최대] 여야 합니다.")
    low, high = float(value[0]), float(value[1])
    if not lo <= low <= high <= hi:
        raise ConfigError(f"'{key}' 은(는) {lo} 이상 {hi} 이하이고 최소가 최대 이하여야 합니다.")
    return low, high


def _require_list(section: dict, key: str, count: int, lo: float, hi: float, ints: bool) -> tuple:
    """길이가 정해진 숫자 목록. 값은 모두 [lo, hi] 안, 단조 증가(같은 값 허용)."""
    value = section.get(key)
    if not isinstance(value, list) or len(value) != count:
        raise ConfigError(f"'{key}' 은(는) 길이 {count} 인 목록이어야 합니다.")
    out = []
    for v in value:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ConfigError(f"'{key}' 의 값은 모두 숫자여야 합니다.")
        if ints and not isinstance(v, int):
            raise ConfigError(f"'{key}' 의 값은 모두 정수여야 합니다.")
        if not lo <= v <= hi:
            raise ConfigError(f"'{key}' 의 값은 {lo} 이상 {hi} 이하여야 합니다. (현재: {v})")
        out.append(int(v) if ints else float(v))
    if any(b < a for a, b in zip(out, out[1:])):
        raise ConfigError(f"'{key}' 은(는) 작은 값부터 순서대로 적어야 합니다.")
    return tuple(out)


def _require_weights(section: dict, key: str) -> dict[str, float]:
    value = section.get(key)
    if not isinstance(value, dict) or set(value) != set(ACTION_WEIGHT_KEYS):
        raise ConfigError(f"'{key}' 은(는) {list(ACTION_WEIGHT_KEYS)} 키를 모두 가진 객체여야 합니다.")
    weights: dict[str, float] = {}
    for name in ACTION_WEIGHT_KEYS:
        w = value[name]
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not 0 <= w <= 1000:
            raise ConfigError(f"'{key}.{name}' 은(는) 0 이상 1000 이하의 숫자여야 합니다.")
        weights[name] = float(w)
    if sum(weights.values()) <= 0:
        raise ConfigError(f"'{key}' 의 가중치 합은 0보다 커야 합니다.")
    return weights


def parse_config(data: dict) -> AppConfig:
    """딕셔너리를 검증된 AppConfig로 변환한다."""
    if not isinstance(data, dict):
        raise ConfigError("설정 최상위 값은 객체(dict)여야 합니다.")

    version = _require_int(data, "version", 1, 10_000)
    if version != SUPPORTED_CONFIG_VERSION:
        raise ConfigError(f"지원하지 않는 설정 버전입니다: {version}")

    display = _require_dict(data, "display")
    debug = _require_dict(data, "debug")
    physics = _require_dict(data, "physics")
    walker = _require_dict(data, "walker")
    swimmer = _require_dict(data, "swimmer")
    pointer = _require_dict(data, "pointer")
    mood = _require_dict(data, "mood")
    needs = _require_dict(data, "needs")
    growth = _require_dict(data, "growth")
    activity = _require_dict(data, "activity")
    food = _require_dict(data, "food")
    toy = _require_dict(data, "toy")

    frame_size = debug.get("placeholder_frame_size")
    if (
        not isinstance(frame_size, list)
        or len(frame_size) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in frame_size)
    ):
        raise ConfigError("'placeholder_frame_size' 은(는) 양의 정수 두 개 [w, h] 여야 합니다.")

    needs_cfg = NeedsConfig(
        start=_require_number(needs, "start", 0, 100),
        decay_per_hour=_require_number(needs, "decay_per_hour", 0, 100),
        hungry_below=_require_number(needs, "hungry_below", 0, 100),
        critical_hours=_require_number(needs, "critical_hours", 0.01, 1000),
        death_hours=_require_number(needs, "death_hours", 0.01, 1000),
        food_amount=_require_number(needs, "food_amount", 0, 100),
        eat_refuse_at=_require_number(needs, "eat_refuse_at", 0, 100),
        eat_duration_s=_require_number(needs, "eat_duration_s", 0.1, 60),
    )
    if needs_cfg.critical_hours >= needs_cfg.death_hours:
        raise ConfigError("'critical_hours' 은(는) 'death_hours' 보다 작아야 합니다.")

    return AppConfig(
        version=version,
        display=DisplayConfig(
            animation_fps=_require_number(display, "animation_fps", 1, 240),
            pet_scale=_require_int(display, "pet_scale", 1, 16),
        ),
        debug=DebugConfig(
            placeholder_frame_size=(frame_size[0], frame_size[1]),
            start_pet=_require_str(debug, "start_pet"),
            time_scale=_require_number(debug, "time_scale", 0.1, 20),
        ),
        physics=PhysicsConfig(
            gravity=_require_number(physics, "gravity", 1, 20_000),
            max_fall_speed=_require_number(physics, "max_fall_speed", 1, 10_000),
            landing_duration_s=_require_number(physics, "landing_duration_s", 0, 5),
            min_surface_width=_require_number(physics, "min_surface_width", 1, 1_000),
            support_tolerance=_require_number(physics, "support_tolerance", 0, 10),
            window_poll_hz=_require_number(physics, "window_poll_hz", 1, 60),
            spawn_height=_require_number(physics, "spawn_height", 0, 5_000),
            max_step_s=_require_number(physics, "max_step_s", 0.001, 1),
        ),
        walker=WalkerConfig(
            walk_speed=_require_number(walker, "walk_speed", 0, 500),
            jump_up_speed=_require_number(walker, "jump_up_speed", 0, 500),
            jump_off_speed=_require_number(walker, "jump_off_speed", 0, 500),
            jump_off_chance=_require_number(walker, "jump_off_chance", 0, 1),
            edge_margin=_require_number(walker, "edge_margin", 0, 100),
            scared_duration_s=_require_pair(walker, "scared_duration_s", 0, 60),
            startled_duration_s=_require_number(walker, "startled_duration_s", 0, 60),
            idle_duration_s=_require_pair(walker, "idle_duration_s", 0, 3600),
            walk_duration_s=_require_pair(walker, "walk_duration_s", 0, 3600),
            sit_duration_s=_require_pair(walker, "sit_duration_s", 0, 3600),
            sleep_duration_s=_require_pair(walker, "sleep_duration_s", 0, 3600),
            action_weights=_require_weights(walker, "action_weights"),
        ),
        swimmer=SwimmerConfig(
            swim_speed=_require_number(swimmer, "swim_speed", 0, 500),
            turn_s=_require_number(swimmer, "turn_s", 0.01, 60),
            retarget_s=_require_pair(swimmer, "retarget_s", 0.1, 3600),
            sink_speed=_require_number(swimmer, "sink_speed", 0, 500),
            startle_radius=_require_number(swimmer, "startle_radius", 0, 2000),
            startle_cursor_speed=_require_number(swimmer, "startle_cursor_speed", 0, 20_000),
            startle_speed=_require_number(swimmer, "startle_speed", 0, 1000),
            startle_duration_s=_require_number(swimmer, "startle_duration_s", 0, 60),
        ),
        pointer=PointerConfig(
            drag_threshold_px=_require_number(pointer, "drag_threshold_px", 0, 1000),
            min_stroke_px=_require_number(pointer, "min_stroke_px", 0, 1000),
            throw_inertia=_require_number(pointer, "throw_inertia", 0, 3),
            max_throw_speed=_require_number(pointer, "max_throw_speed", 0, 10_000),
            velocity_window_s=_require_number(pointer, "velocity_window_s", 0.01, 1),
        ),
        mood=MoodConfig(
            start=_require_number(mood, "start", 0, 100),
            pet_gain=_require_number(mood, "pet_gain", 0, 100),
            pet_joy_duration_s=_require_number(mood, "pet_joy_duration_s", 0, 60),
            drop_penalty=_require_number(mood, "drop_penalty", 0, 100),
            decay_per_s=_require_number(mood, "decay_per_s", 0, 100),
            sad_below=_require_number(mood, "sad_below", 0, 100),
        ),
        needs=needs_cfg,
        growth=GrowthConfig(
            hours=_require_list(growth, "hours", 4, 0, 100_000, ints=False),
            meals=_require_list(growth, "meals", 4, 0, 100_000, ints=True),
            pixel_scale=_require_list(growth, "pixel_scale", 5, 1, 16, ints=True),
        ),
        activity=ActivityConfig(
            idle_pause_s=_require_number(activity, "idle_pause_s", 1, 86_400),
            autosave_s=_require_number(activity, "autosave_s", 5, 3600),
        ),
        food=FoodConfig(
            lifetime_s=_require_number(food, "lifetime_s", 1, 3600),
            max_items=_require_int(food, "max_items", 1, 50),
        ),
        toy=ToyConfig(
            play_s=_require_number(toy, "play_s", 1, 3600),
            push_speed=_require_number(toy, "push_speed", 0, 500),
            friction=_require_number(toy, "friction", 0, 10_000),
        ),
    )


def load_config(path: Path) -> AppConfig:
    """설정 파일을 읽어 검증된 AppConfig를 반환한다."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"설정 파일을 읽을 수 없습니다: {path} ({exc})") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"설정 파일 JSON 형식 오류: {path} ({exc})") from exc
    return parse_config(data)
