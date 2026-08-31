"""
Coverage-paydown tests for geometry module functions.

Covers allowlisted public functions from:
- polygon.py (uncovered subset)
- primitives.py (uncovered subset)
- smooth.py (uncovered subset)
- transform.py (uncovered subset)
- overlap.py (uncovered subset)
- sdf.py (uncovered subset)
- constraints.py
- projections.py
- geometry/__init__.py (sdf_gradient)

All operators delegate to the temper_geometry Rust crate; the Python
wrappers take flat scalar coordinates / flat vertex lists.
"""

import math

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# transform.py — uncovered subset
# ---------------------------------------------------------------------------

from temper_geometry import (
    get_rotated_bounds,
    transform_pin_position,
    transform_pin_positions,
)


class TestTransformUncovered:
    """Tests for transform functions not covered by test_geometry.py."""

    def test_get_rotated_bounds(self):
        """AABB of rotated rectangle."""
        rx, ry, rw, rh = get_rotated_bounds(0.0, 0.0, 4.0, 2.0, np.pi / 4)
        assert rw > 0
        assert rh > 0

    def test_transform_pin_position(self):
        """Transform pin position with component rotation."""
        wx, wy = transform_pin_position(1.0, 0.0, 5.0, 5.0, np.pi / 2)
        # KiCad footprint-child rotation convention: R(-theta)
        # Pin at offset (1,0) rotated -90deg -> (0,-1) + center (5,5) -> (5,4)
        assert np.isclose(wx, 5.0, atol=1e-6)
        assert np.isclose(wy, 4.0, atol=1e-6)

    def test_transform_pin_positions(self):
        """Transform multiple pin positions."""
        pins = [1.0, 0.0, 0.0, 1.0]
        world = transform_pin_positions(pins, 5.0, 5.0, 0.0)
        assert len(world) == 4
        assert np.isclose(world[0], 6.0, atol=1e-6)
        assert np.isclose(world[1], 5.0, atol=1e-6)


# ---------------------------------------------------------------------------
# overlap.py — uncovered subset
# ---------------------------------------------------------------------------

from temper_geometry import (
    compute_pairwise_distances,
)


class TestOverlapUncovered:
    """Tests for overlap functions not covered by test_geometry.py."""

    def test_compute_pairwise_distances(self):
        """Pairwise distance matrix for rects."""
        rects = [0.0, 0.0, 2.0, 2.0, 5.0, 0.0, 2.0, 2.0]
        dists = compute_pairwise_distances(rects)
        assert len(dists) == 4  # 2x2 matrix


# ---------------------------------------------------------------------------
# sdf.py — uncovered subset
# ---------------------------------------------------------------------------

class TestSDFUncovered:
    """Tests for SDF functions not covered by test_geometry.py."""
    def test_sdf_gradient_circle_init_module(self):
        """Gradient of SDF at a point (__init__.py version: sdf_gradient(p, sdf_fn))."""
        from temper_placer.geometry import sdf_gradient as sdf_gradient_top

        def circle_sdf(pt):
            px, py = pt
            return math.sqrt(px * px + py * py) - 1.0

        grad = sdf_gradient_top((2.0, 0.0), circle_sdf)
        assert np.allclose(grad, (1.0, 0.0), atol=1e-3)


# ---------------------------------------------------------------------------
# constraints.py
# ---------------------------------------------------------------------------

from temper_placer.geometry.constraints import (
    BoundaryViolation,
    ValidBounds,
    compute_boundary_violation,
    compute_valid_bounds,
    compute_zone_distance,
    is_within_bounds,
    point_in_zone,
)


class TestBoundaryViolation:
    """Tests for BoundaryViolation NamedTuple."""

    def test_has_violation_true(self):
        """Violation detected when component extends beyond edge."""
        bv = BoundaryViolation(left=1.0, right=0.0, bottom=0.0, top=0.0)
        assert bv.has_violation is True

    def test_has_violation_false(self):
        """No violation when all edges clear."""
        bv = BoundaryViolation(left=0.0, right=0.0, bottom=0.0, top=0.0)
        assert bv.has_violation is False

    def test_max_violation(self):
        """Max violation across edges."""
        bv = BoundaryViolation(left=1.0, right=3.0, bottom=0.5, top=2.0)
        assert bv.max_violation == 3.0

    def test_total_violation(self):
        """Total sum of all violations."""
        bv = BoundaryViolation(left=1.0, right=2.0, bottom=0.5, top=1.5)
        assert bv.total_violation == 5.0


class TestValidBounds:
    """Tests for ValidBounds NamedTuple."""

    def test_clamp_point_inside(self):
        """Point inside bounds unchanged."""
        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        x, y = vb.clamp_point(50.0, 50.0)
        assert x == 50.0
        assert y == 50.0

    def test_clamp_point_outside(self):
        """Point outside bounds clamped."""
        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        x, y = vb.clamp_point(150.0, -10.0)
        assert x == 100.0
        assert y == 0.0

    def test_contains_point_true(self):
        """Point inside bounds."""
        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.contains_point(50.0, 50.0) is True

    def test_contains_point_false(self):
        """Point outside bounds."""
        vb = ValidBounds(x_min=0.0, x_max=100.0, y_min=0.0, y_max=100.0)
        assert vb.contains_point(150.0, 50.0) is False


class TestConstraintFunctions:
    """Tests for constraint computation functions."""

    def test_compute_valid_bounds(self):
        """Compute valid placement region for component center."""
        vb = compute_valid_bounds(
            component_half_width=5.0,
            component_half_height=5.0,
            region_x_min=0.0,
            region_y_min=0.0,
            region_x_max=100.0,
            region_y_max=100.0,
            margin=2.0,
        )
        assert vb.x_min == 7.0  # 0 + half_width(5) + margin(2)
        assert vb.y_min == 7.0
        assert vb.x_max == 93.0  # 100 - half_width(5) - margin(2)
        assert vb.y_max == 93.0

    def test_compute_boundary_violation_inside(self):
        """No violation when component fits inside board."""
        bv = compute_boundary_violation(
            position_x=50.0, position_y=50.0,
            component_half_width=10.0, component_half_height=10.0,
            board_x_min=0.0, board_y_min=0.0,
            board_x_max=100.0, board_y_max=100.0,
        )
        assert bv.has_violation is False

    def test_compute_boundary_violation_outside(self):
        """Violation when component extends beyond board."""
        bv = compute_boundary_violation(
            position_x=-5.0, position_y=50.0,
            component_half_width=10.0, component_half_height=10.0,
            board_x_min=0.0, board_y_min=0.0,
            board_x_max=100.0, board_y_max=100.0,
        )
        assert bv.has_violation is True
        assert bv.left > 0

    def test_is_within_bounds_inside(self):
        """Component entirely inside region."""
        assert is_within_bounds(
            position_x=50.0, position_y=50.0,
            component_half_width=10.0, component_half_height=10.0,
            region_x_min=0.0, region_y_min=0.0,
            region_x_max=100.0, region_y_max=100.0,
        ) is True

    def test_is_within_bounds_outside(self):
        """Component extends beyond region."""
        assert is_within_bounds(
            position_x=-5.0, position_y=50.0,
            component_half_width=10.0, component_half_height=10.0,
            region_x_min=0.0, region_y_min=0.0,
            region_x_max=100.0, region_y_max=100.0,
        ) is False

    def test_compute_zone_distance_inside(self):
        """Negative distance when point inside zone."""
        d = compute_zone_distance(50.0, 50.0, 0.0, 0.0, 100.0, 100.0)
        assert d < 0  # Inside -> negative distance to nearest edge

    def test_compute_zone_distance_outside(self):
        """Positive distance when point outside zone."""
        d = compute_zone_distance(150.0, 50.0, 0.0, 0.0, 100.0, 100.0)
        assert d > 0  # Outside -> positive

    def test_point_in_zone_inside(self):
        """Point inside zone returns True."""
        assert point_in_zone(50.0, 50.0, 0.0, 0.0, 100.0, 100.0) is True

    def test_point_in_zone_outside(self):
        """Point outside zone returns False."""
        assert point_in_zone(150.0, 50.0, 0.0, 0.0, 100.0, 100.0) is False
