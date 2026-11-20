"""도트 그림 렌더링과 클릭 영역 계산을 위한 순수 함수 모음 (Qt 비의존)."""

from __future__ import annotations

from typing import Sequence

# 이 값 이상의 알파를 가진 픽셀만 "불투명"으로 보고 마우스 입력을 받는다.
DEFAULT_ALPHA_THRESHOLD = 128

# (y, x_start, x_end) — x_end는 배타적(exclusive) 끝 좌표
Run = tuple[int, int, int]


def physical_scale(base_scale: int, dpr: float) -> int:
    """물리 픽셀 기준 정수 확대 배율을 구한다.

    예) base_scale=4, dpr=1.25 -> 5 (물리 5배 확대 후 창 논리 크기는 4배와 같음)
    정수 배율이므로 최근접 이웃 확대 시 픽셀 크기가 균일하게 유지된다.
    """
    if base_scale < 1:
        raise ValueError("base_scale 은 1 이상이어야 합니다.")
    if dpr <= 0:
        raise ValueError("dpr 은 0보다 커야 합니다.")
    return max(1, round(base_scale * dpr))


def scale_runs(runs: Sequence[Run], factor: int) -> list[Run]:
    """원본 픽셀 기준 구간을 정수 배율 factor만큼 확대한 구간으로 바꾼다.

    최근접 이웃 확대와 같은 격자를 쓰므로 클릭 영역도 그림과 정확히 맞는다.
    """
    if factor < 1:
        raise ValueError("factor 는 1 이상이어야 합니다.")
    scaled: list[Run] = []
    for y, x0, x1 in runs:
        for dy in range(factor):
            scaled.append((y * factor + dy, x0 * factor, x1 * factor))
    return scaled


def opaque_runs(
    alpha_rows: Sequence[Sequence[int]],
    threshold: int = DEFAULT_ALPHA_THRESHOLD,
) -> list[Run]:
    """알파 값 행렬에서 불투명 구간(run)을 행 단위로 추출한다.

    반환된 구간들의 합집합이 클릭을 받는 영역이 된다.
    """
    runs: list[Run] = []
    for y, row in enumerate(alpha_rows):
        x = 0
        width = len(row)
        while x < width:
            if row[x] >= threshold:
                start = x
                while x < width and row[x] >= threshold:
                    x += 1
                runs.append((y, start, x))
            else:
                x += 1
    return runs
