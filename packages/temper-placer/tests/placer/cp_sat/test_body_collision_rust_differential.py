"""Differential proof for the Rust-owned F.Fab geometry authority."""

from __future__ import annotations

import pytest
import temper_geometry as _rust

import tests.placer.cp_sat._body_collision_py_oracle as _oracle

assert hasattr(_rust, "fab_body_validate_py"), "Rust F.Fab validation is not imported"
assert hasattr(_rust, "fab_body_relations_batch_py"), "Rust F.Fab batch API is not imported"


def _rust_relation(points_a, pose_a, points_b, pose_b):
    relations = _rust.fab_body_relations_batch_py(
        ["A", "B"],
        [
            [value for point in points_a for value in point],
            [value for point in points_b for value in point],
        ],
        [(pose_a[0], pose_a[1]), (pose_b[0], pose_b[1])],
        [pose_a[2], pose_b[2]],
    )
    _a, _b, kind, area = relations[0]
    return kind, area


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
def test_relation_and_area_match_independent_shapely_oracle(points_a, pose_a, points_b, pose_b):
    expected_kind, expected_area = _oracle.classify(points_a, pose_a, points_b, pose_b)
    actual_kind, actual_area = _rust_relation(points_a, pose_a, points_b, pose_b)
    assert actual_kind == expected_kind
    assert actual_area == pytest.approx(expected_area, abs=1e-9)


def test_invalid_geometry_and_rotation_fail_at_rust_boundary():
    with pytest.raises(ValueError, match="even"):
        _rust_relation(
            [(0.0, 0.0), (1.0,)], (0.0, 0.0, 0), [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)], (0.0, 0.0, 0)
        )
    with pytest.raises(ValueError, match="0..=3"):
        _rust_relation(
            [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
            (0.0, 0.0, 4),
            [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
            (0.0, 0.0, 0),
        )


def test_courtyard_only_aabb_overlap_is_not_a_body_collision():
    relation, area = _rust_relation(
        [(0.0, 0.0), (4.0, 0.0), (0.0, 4.0)],
        (0.0, 0.0, 0),
        [(4.0, 4.0), (8.0, 4.0), (4.0, 8.0)],
        (0.0, 0.0, 0),
    )
    assert relation == "clear"
    assert area == 0.0


def test_rust_owns_tolerance_and_standalone_body_validation():
    assert pytest.approx(1e-6) == _rust.AREA_TOLERANCE_MM2
    assert _rust.fab_body_validate_py("A", [0.0, 0.0, 1.0, 0.0, 0.0, 1.0])
    with pytest.raises(ValueError, match="self-intersecting"):
        _rust.fab_body_validate_py("A", [0.0, 0.0, 3.0, 3.0, 0.0, 2.0, 2.0, 0.0])


def test_batch_relations_are_sorted_and_match_pairwise_authority():
    refs = ["C", "A", "B"]
    points = [
        [-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0],
        [-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0],
        [-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0],
    ]
    relations = _rust.fab_body_relations_batch_py(
        refs,
        points,
        [(20.0, 0.0), (0.0, 0.0), (1.0, 0.0)],
        [0, 0, 0],
    )
    assert [(ref_a, ref_b) for ref_a, ref_b, _kind, _area in relations] == [
        ("A", "B"),
        ("A", "C"),
        ("B", "C"),
    ]
    assert relations[0][2] == "overlap"
    assert relations[1][2] == "clear"
    assert relations[2][2] == "clear"
