import pytest

from core.render_math import opaque_runs, physical_scale, scale_runs


def test_opaque_runs_finds_row_segments():
    alpha = [
        [0, 255, 255, 0],
        [255, 0, 0, 255],
        [0, 0, 0, 0],
    ]
    assert opaque_runs(alpha) == [(0, 1, 3), (1, 0, 1), (1, 3, 4)]


def test_opaque_runs_threshold_is_inclusive():
    alpha = [[127, 128, 200]]
    assert opaque_runs(alpha, threshold=128) == [(0, 1, 3)]


def test_opaque_runs_empty_image():
    assert opaque_runs([]) == []
    assert opaque_runs([[0, 0]]) == []


def test_scale_runs_matches_nearest_neighbor_grid():
    runs = [(0, 1, 3)]  # 원본 1행, x 1~2
    scaled = scale_runs(runs, 3)
    assert scaled == [(0, 3, 9), (1, 3, 9), (2, 3, 9)]


def test_scale_runs_factor_one_is_identity():
    runs = [(2, 0, 4), (5, 1, 2)]
    assert scale_runs(runs, 1) == runs


def test_scale_runs_rejects_zero_factor():
    with pytest.raises(ValueError):
        scale_runs([(0, 0, 1)], 0)


@pytest.mark.parametrize(
    "base, dpr, expected",
    [
        (4, 1.0, 4),
        (4, 1.25, 5),
        (4, 1.5, 6),
        (4, 2.0, 8),
        (1, 0.5, 1),  # 최소 1배율 보장
    ],
)
def test_physical_scale(base, dpr, expected):
    assert physical_scale(base, dpr) == expected


def test_physical_scale_rejects_invalid_input():
    with pytest.raises(ValueError):
        physical_scale(0, 1.0)
    with pytest.raises(ValueError):
        physical_scale(4, 0)
