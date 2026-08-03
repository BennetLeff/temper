"""Unit tests for the sanctioned KiCad rotation convention module.

The convention itself (R(-theta)) is proven against real ``kicad-cli`` DRC
output in
``docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md``
Sec. 2 -- this file is not re-proving the convention, it is locking down
this specific implementation's arithmetic (round-trip inverse, the shapely
sign helper, the degrees/radians wrappers, and the documented 90-degree
closed forms) so a future edit here cannot silently drift.
"""

from __future__ import annotations

import math

import pytest
from shapely.affinity import rotate as shapely_rotate
from shapely.geometry import Point as ShapelyPoint

from temper_placer.geometry.kicad_transform import (
    place_local_to_world,
    rotate_local_to_world,
    rotate_local_to_world_deg,
    rotate_world_to_local,
    rotate_world_to_local_deg,
    shapely_rotation_angle_deg,
)


@pytest.mark.parametrize(
    ("angle_deg", "expected"),
    [
        (0.0, (5.0, 0.0)),
        (90.0, (0.0, -5.0)),
        (180.0, (-5.0, 0.0)),
        (270.0, (0.0, 5.0)),
    ],
)
def test_rotate_local_to_world_matches_ground_truth_experiment(angle_deg, expected):
    """Reproduces the exact scenario from the evidence doc's ground-truth
    experiment: a pad at local offset (5, 0) on a footprint rotated by
    ``angle_deg`` must land where real kicad-cli DRC placed it."""
    result = rotate_local_to_world_deg(5.0, 0.0, angle_deg)
    assert result[0] == pytest.approx(expected[0], abs=1e-9)
    assert result[1] == pytest.approx(expected[1], abs=1e-9)


# Closed-form quadrant law R(-theta) at the finite angle set: 0 -> (x, y),
# 90 -> (y, -x), 180 -> (-x, -y), 270 -> (-y, x). Expected rows are the
# integer-entry values this law gives for each offset, so a sign flip
# (R(+theta): 90 -> (-y, x), 270 -> (y, -x)) fails these immediately --
# e.g. (2.0, -1.0) at 90 degrees: R(-90) -> (-1, -2) but R(+90) -> (1, 2).
# This extends the single-offset ground-truth parametrization above to
# several offsets including fully asymmetric ones (plan 011 U1).
@pytest.mark.parametrize(
    ("angle_deg", "offset", "expected"),
    [
        (0.0, (0.5, 0.3), (0.5, 0.3)),
        (90.0, (0.5, 0.3), (0.3, -0.5)),
        (180.0, (0.5, 0.3), (-0.5, -0.3)),
        (270.0, (0.5, 0.3), (-0.3, 0.5)),
        (0.0, (2.0, -1.0), (2.0, -1.0)),
        (90.0, (2.0, -1.0), (-1.0, -2.0)),
        (180.0, (2.0, -1.0), (-2.0, 1.0)),
        (270.0, (2.0, -1.0), (1.0, 2.0)),
        (0.0, (3.7, -2.1), (3.7, -2.1)),
        (90.0, (3.7, -2.1), (-2.1, -3.7)),
        (180.0, (3.7, -2.1), (-3.7, 2.1)),
        (270.0, (3.7, -2.1), (2.1, 3.7)),
    ],
)
def test_rotate_local_to_world_closed_form_at_quadrant_angles(angle_deg, offset, expected):
    """Convention-anchored expected values at every angle of the finite set
    for several offsets, including fully asymmetric ones -- the closed-form
    quadrant law, which a sign flip violates at 90 and 270 degrees."""
    result = rotate_local_to_world_deg(offset[0], offset[1], angle_deg)
    assert result[0] == pytest.approx(expected[0], abs=1e-9)
    assert result[1] == pytest.approx(expected[1], abs=1e-9)


@pytest.mark.parametrize("angle_deg", [0.0, 30.0, 90.0, 137.0, 180.0, 270.0, -45.0, 400.0])
def test_world_to_local_is_the_inverse(angle_deg):
    x, y = 3.7, -2.1
    theta = math.radians(angle_deg)
    wx, wy = rotate_local_to_world(x, y, theta)
    lx, ly = rotate_world_to_local(wx, wy, theta)
    assert lx == pytest.approx(x, abs=1e-9)
    assert ly == pytest.approx(y, abs=1e-9)


def test_place_local_to_world_adds_origin():
    rx, ry = rotate_local_to_world(2.0, -1.0, math.radians(90.0))
    px, py = place_local_to_world(2.0, -1.0, 100.0, 200.0, math.radians(90.0))
    assert px == pytest.approx(100.0 + rx, abs=1e-9)
    assert py == pytest.approx(200.0 + ry, abs=1e-9)


@pytest.mark.parametrize("angle_deg", [0.0, 15.0, 90.0, 180.0, 270.0, 333.0])
def test_shapely_rotation_angle_matches_point_rotation(angle_deg):
    """shapely.affinity.rotate(..., shapely_rotation_angle_deg(theta)) must
    move a point the same place as rotate_local_to_world_deg(theta)."""
    x, y = 4.2, 6.6
    expected = rotate_local_to_world_deg(x, y, angle_deg)
    rotated = shapely_rotate(
        ShapelyPoint(x, y), shapely_rotation_angle_deg(angle_deg), origin=(0, 0)
    )
    assert rotated.x == pytest.approx(expected[0], abs=1e-9)
    assert rotated.y == pytest.approx(expected[1], abs=1e-9)


def test_degrees_and_radians_wrappers_agree():
    x, y, angle_deg = 1.5, -3.25, 62.0
    assert rotate_local_to_world_deg(x, y, angle_deg) == pytest.approx(
        rotate_local_to_world(x, y, math.radians(angle_deg))
    )
    assert rotate_world_to_local_deg(x, y, angle_deg) == pytest.approx(
        rotate_world_to_local(x, y, math.radians(angle_deg))
    )
