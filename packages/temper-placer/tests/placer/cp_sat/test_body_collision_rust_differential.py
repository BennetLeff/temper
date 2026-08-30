"""Differential proof for the Rust-owned F.Fab geometry authority."""

from __future__ import annotations

import pytest
import temper_geometry as _rust

import tests.placer.cp_sat._body_collision_py_oracle as _oracle


assert hasattr(_rust, "fab_body_overlap_py"), "Rust F.Fab authority is not imported"


def _rust_relation(points_a, pose_a, points_b, pose_b):
    return _rust.fab_body_overlap_py(
        "A", [value for point in points_a for value in point], *pose_a,
        "B", [value for point in points_b for value in point], *pose_b,
    )


@pytest.mark.parametrize(
    ("points_a", "pose_a", "points_b", "pose_b"),
    [
        (
            [(0.0, 0.0), (4.0, 0.0), (0.0, 4.0)],
            (0.0, 0.0, 0),
            [(4.0, 4.0), (8.0, 4.0), (4.0, 8.0)],
            (0.0, 0.0, 0),
        ),
        (
            [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
            (0.0, 0.0, 0),
            [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
            (0.5, 0.0, 1),
        ),
        (
            [(-3.0, -2.0), (0.0, -2.0), (0.0, -1.0), (3.0, -1.0), (3.0, 2.0), (-3.0, 2.0)],
            (12.25, -8.5, 3),
            [(-1.0, -3.0), (2.0, -3.0), (2.0, 3.0), (-1.0, 3.0)],
            (13.0, -8.0, 2),
        ),
    ],
)
def test_relation_and_area_match_independent_shapely_oracle(
    points_a, pose_a, points_b, pose_b
):
    expected_kind, expected_area = _oracle.classify(points_a, pose_a, points_b, pose_b)
    actual_kind, actual_area = _rust_relation(points_a, pose_a, points_b, pose_b)
    assert actual_kind == expected_kind
    assert actual_area == pytest.approx(expected_area, abs=1e-9)


def test_invalid_geometry_and_rotation_fail_at_rust_boundary():
    with pytest.raises(ValueError, match="even"):
        _rust.fab_body_overlap_py("A", [0.0, 0.0, 1.0], 0.0, 0.0, 0, "B", [0.0, 0.0, 1.0, 0.0, 0.0, 1.0], 0.0, 0.0, 0)
    with pytest.raises(ValueError, match="0..=3"):
        _rust.fab_body_overlap_py("A", [0.0, 0.0, 1.0, 0.0, 0.0, 1.0], 0.0, 0.0, 4, "B", [0.0, 0.0, 1.0, 0.0, 0.0, 1.0], 0.0, 0.0, 0)


def test_courtyard_only_aabb_overlap_is_not_a_body_collision():
    relation, area = _rust_relation(
        [(0.0, 0.0), (4.0, 0.0), (0.0, 4.0)],
        (0.0, 0.0, 0),
        [(4.0, 4.0), (8.0, 4.0), (4.0, 8.0)],
        (0.0, 0.0, 0),
    )
    assert relation == "clear"
    assert area == 0.0
