"""설정 파일(config/settings.json) 로딩과 검증.

이 모듈은 Qt에 의존하지 않는다. 모든 수치는 설정 파일에 있으며,
여기서는 타입과 범위만 검증한다.

물리/행동 수치 단위: 별도 표기가 없으면 "원본 픽셀"(스프라이트 한 칸 기준)이다.
실행 시 DPI 배율을 곱해 물리 픽셀로 바꾼다.
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
    pet_scale: int  # 논리 픽셀 기준 정수 배율 (DPI 배율은 별도로 곱해진다)


@dataclass(frozen=True)
class DebugConfig:
    placeholder_frame_size: tuple[int, int]
    start_pet: str  # 저장 데이터 도입 전 임시로 띄울 동물 폴더 이름


@dataclass(frozen=True)
class PhysicsConfig:
    gravity: float            # 원본 px/s^2
    max_fall_speed: float     # 원본 px/s
    landing_duration_s: float
    min_surface_width: float  # 원본 px. 이보다 짧은 발판은 무시
    support_tolerance: float  # 원본 px. 발판 높이 판정 허용 오차
    window_poll_hz: float     # 창 목록 갱신 빈도
    spawn_height: float       # 원본 px. 펫을 처음 놓는 높이 (작업 영역 윗변 위)
    max_step_s: float         # 한 번의 갱신에 시뮬레이션하는 최대 시간(초)


@dataclass(frozen=True)
class WalkerConfig:
    walk_speed: float         # 원본 px/s
    jump_up_speed: float      # 원본 px/s (뛰어내릴 때 살짝 위로 튀는 속도)
    jump_off_speed: float     # 원본 px/s (가장자리에서 밖으로 밀리는 속도)
    jump_off_chance: float    # 0~1, 가장자리에서 용기를 내어 뛰어내릴 확률
    edge_margin: float        # 원본 px. 가장자리에서 이만큼 떨어진 곳에서 멈춤
    scared_duration_s: tuple[float, float]
    startled_duration_s: float
    idle_duration_s: tuple[float, float]
    walk_duration_s: tuple[float, float]
    sit_duration_s: tuple[float, float]
    sleep_duration_s: tuple[float, float]
    action_weights: dict[str, float]


@dataclass(frozen=True)
class AppConfig:
    version: int
    display: DisplayConfig
    debug: DebugConfig
    physics: PhysicsConfig
    walker: WalkerConfig


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

    frame_size = debug.get("placeholder_frame_size")
    if (
        not isinstance(frame_size, list)
        or len(frame_size) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in frame_size)
    ):
        raise ConfigError("'placeholder_frame_size' 은(는) 양의 정수 두 개 [w, h] 여야 합니다.")

    return AppConfig(
        version=version,
        display=DisplayConfig(
            animation_fps=_require_number(display, "animation_fps", 1, 240),
            pet_scale=_require_int(display, "pet_scale", 1, 16),
        ),
        debug=DebugConfig(
            placeholder_frame_size=(frame_size[0], frame_size[1]),
            start_pet=_require_str(debug, "start_pet"),
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
