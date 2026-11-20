"""설정 파일(config/settings.json) 로딩과 검증.

이 모듈은 Qt에 의존하지 않는다. 모든 수치는 설정 파일에 있으며,
여기서는 타입과 범위만 검증한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_CONFIG_VERSION = 1


class ConfigError(ValueError):
    """설정 파일 내용이 잘못되었을 때 발생한다."""


@dataclass(frozen=True)
class DisplayConfig:
    animation_fps: float
    pet_scale: int  # 논리 픽셀 기준 정수 배율 (DPI 배율은 별도로 곱해진다)


@dataclass(frozen=True)
class DebugConfig:
    placeholder_frame_size: tuple[int, int]


@dataclass(frozen=True)
class AppConfig:
    version: int
    display: DisplayConfig
    debug: DebugConfig


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


def parse_config(data: dict) -> AppConfig:
    """딕셔너리를 검증된 AppConfig로 변환한다."""
    if not isinstance(data, dict):
        raise ConfigError("설정 최상위 값은 객체(dict)여야 합니다.")

    version = _require_int(data, "version", 1, 10_000)
    if version != SUPPORTED_CONFIG_VERSION:
        raise ConfigError(f"지원하지 않는 설정 버전입니다: {version}")

    display = _require_dict(data, "display")
    debug = _require_dict(data, "debug")

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
