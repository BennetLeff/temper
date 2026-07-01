"""Unit tests for C-CAP projection operators.

Tests cover:
- Zone containment: inside → identity, outside → clamped to nearest boundary
- Keepout avoidance: inside → nearest external edge, outside → identity
- Board bounds: inside → identity, outside → clamped
- Half-plane: violating → boundary, feasible → identity
- Edge-strip: clamps to edge-adjacent strip
- Manufacturing side: clamps to top/bottom half
- Identity projection: returns unchanged
- Idempotence: P(P(x)) == P(x) for all operators
"""

import jax.numpy as jnp
import pytest

from temper_placer.geometry.projections import (
    identity_projection,
    project_onto_board,
    project_onto_edge_strip,
    project_onto_half_plane,
    project_onto_side,
    project_onto_zone,
    project_outside_keepout,
)


# ---------------------------------------------------------------------------
# project_onto_zone
# ---------------------------------------------------------------------------


class TestProjectOntoZone:
    RECT_ZONE = jnp.array(
        [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]], dtype=jnp.float32
    )

    def test_inside_rect_identity(self):
        """Point inside rect zone returns unchanged."""
        result = project_onto_zone(jnp.array([5.0, 5.0]), self.RECT_ZONE)
        assert jnp.allclose(result, jnp.array([5.0, 5.0]))

    def test_outside_left_clamped(self):
        """Point left of rect clamped to left edge."""
        result = project_onto_zone(jnp.array([-5.0, 5.0]), self.RECT_ZONE)
        assert jnp.allclose(result, jnp.array([0.0, 5.0]))

    def test_outside_right_clamped(self):
        """Point right of rect clamped to right edge."""
        result = project_onto_zone(jnp.array([15.0, 5.0]), self.RECT_ZONE)
        assert jnp.allclose(result, jnp.array([10.0, 5.0]))

    def test_outside_top_clamped(self):
        """Point above rect clamped to top edge."""
        result = project_onto_zone(jnp.array([5.0, 15.0]), self.RECT_ZONE)
        assert jnp.allclose(result, jnp.array([5.0, 10.0]))

    def test_outside_bottom_clamped(self):
        """Point below rect clamped to bottom edge."""
        result = project_onto_zone(jnp.array([5.0, -5.0]), self.RECT_ZONE)
        assert jnp.allclose(result, jnp.array([5.0, 0.0]))

    def test_with_half_size(self):
        """Component half-size shrinks interior."""
        result = project_onto_zone(jnp.array([-5.0, 5.0]), self.RECT_ZONE, half_w=2.0, half_h=2.0)
        assert jnp.allclose(result, jnp.array([2.0, 5.0]))

    def test_with_half_size_inside(self):
        """Point inside shrunken zone returns unchanged."""
        result = project_onto_zone(
            jnp.array([7.0, 7.0]), self.RECT_ZONE, half_w=2.0, half_h=2.0
        )
        assert jnp.allclose(result, jnp.array([7.0, 7.0]))

    @pytest.mark.parametrize("point", [
        jnp.array([3.0, 3.0]),
        jnp.array([8.0, 8.0]),
        jnp.array([5.0, 5.0]),
    ])
    def test_idempotent(self, point):
        """P(P(x)) == P(x) for convex zone."""
        p1 = project_onto_zone(point, self.RECT_ZONE)
        p2 = project_onto_zone(p1, self.RECT_ZONE)
        assert jnp.allclose(p1, p2, atol=1e-6)


# ---------------------------------------------------------------------------
# project_outside_keepout
# ---------------------------------------------------------------------------


class TestProjectOutsideKeepout:
    KEEPOUT = (5.0, 5.0, 10.0, 10.0)

    def test_outside_keepout_identity(self):
        """Point outside keepout returns unchanged."""
        result = project_outside_keepout(jnp.array([1.0, 1.0]), self.KEEPOUT)
        assert jnp.allclose(result, jnp.array([1.0, 1.0]))

    def test_inside_keepout_projected(self):
        """Point inside keepout projected to nearest edge."""
        result = project_outside_keepout(jnp.array([7.5, 7.5]), self.KEEPOUT)
        # Nearest edge from center (7.5, 7.5) is left at x=5
        assert jnp.allclose(result, jnp.array([5.0, 7.5]))

    def test_on_keepout_edge_identity(self):
        """Point on keepout boundary returns unchanged."""
        result = project_outside_keepout(jnp.array([5.0, 7.5]), self.KEEPOUT)
        assert jnp.allclose(result, jnp.array([5.0, 7.5]))

    def test_with_half_size_expands_keepout(self):
        """Half-size expands keepout outward."""
        result = project_outside_keepout(
            jnp.array([8.0, 8.0]), self.KEEPOUT, half_w=3.0, half_h=3.0
        )
        # Expanded keepout (2, 2, 13, 13); (8, 8) is inside → nearest edges
        # are right (13, 8) and top (8, 13), both at distance 5.
        # argmin with ties picks first, so right edge.
        assert jnp.allclose(result, jnp.array([13.0, 8.0]))

    @pytest.mark.parametrize("point", [
        jnp.array([1.0, 1.0]),
        jnp.array([12.0, 12.0]),
    ])
    def test_idempotent(self, point):
        """P(P(x)) == P(x)."""
        p1 = project_outside_keepout(point, self.KEEPOUT)
        p2 = project_outside_keepout(p1, self.KEEPOUT)
        assert jnp.allclose(p1, p2, atol=1e-6)


# ---------------------------------------------------------------------------
# project_onto_board
# ---------------------------------------------------------------------------


class TestProjectOntoBoard:
    BOARD_W = 100.0
    BOARD_H = 100.0
    MARGIN = 3.0

    def test_inside_identity(self):
        """Point inside board margins returns unchanged."""
        result = project_onto_board(jnp.array([50.0, 50.0]), self.MARGIN, self.BOARD_W, self.BOARD_H)
        assert jnp.allclose(result, jnp.array([50.0, 50.0]))

    def test_below_left_corner_clamped(self):
        """Point below minimum x and y clamped."""
        result = project_onto_board(jnp.array([-1.0, -1.0]), self.MARGIN, self.BOARD_W, self.BOARD_H)
        assert jnp.allclose(result, jnp.array([3.0, 3.0]))

    def test_above_right_corner_clamped(self):
        """Point above maximum x and y clamped."""
        result = project_onto_board(jnp.array([102.0, 105.0]), self.MARGIN, self.BOARD_W, self.BOARD_H)
        assert jnp.allclose(result, jnp.array([97.0, 97.0]))

    @pytest.mark.parametrize("point", [
        jnp.array([10.0, 10.0]),
        jnp.array([90.0, 90.0]),
    ])
    def test_idempotent(self, point):
        """P(P(x)) == P(x)."""
        p1 = project_onto_board(point, self.MARGIN, self.BOARD_W, self.BOARD_H)
        p2 = project_onto_board(p1, self.MARGIN, self.BOARD_W, self.BOARD_H)
        assert jnp.allclose(p1, p2, atol=1e-6)


# ---------------------------------------------------------------------------
# project_onto_half_plane
# ---------------------------------------------------------------------------


class TestProjectOntoHalfPlane:
    def test_hv_above_boundary_identity(self):
        """Point above boundary, HV sign (+1), identity."""
        result = project_onto_half_plane(jnp.array([50.0, 30.0]), 20.0, 1.0)
        assert jnp.allclose(result, jnp.array([50.0, 30.0]))

    def test_hv_below_boundary_projected(self):
        """Point below boundary, HV sign (+1), projected to boundary."""
        result = project_onto_half_plane(jnp.array([50.0, 10.0]), 20.0, 1.0)
        assert jnp.allclose(result, jnp.array([50.0, 20.0]))

    def test_lv_below_boundary_identity(self):
        """Point below boundary, LV sign (-1), identity."""
        result = project_onto_half_plane(jnp.array([50.0, 10.0]), 20.0, -1.0)
        assert jnp.allclose(result, jnp.array([50.0, 10.0]))

    def test_lv_above_boundary_projected(self):
        """Point above boundary, LV sign (-1), projected to boundary."""
        result = project_onto_half_plane(jnp.array([50.0, 30.0]), 20.0, -1.0)
        assert jnp.allclose(result, jnp.array([50.0, 20.0]))

    @pytest.mark.parametrize("point", [
        jnp.array([10.0, 5.0]),
        jnp.array([80.0, 95.0]),
    ])
    def test_idempotent(self, point):
        """P(P(x)) == P(x) for convex half-plane."""
        p1 = project_onto_half_plane(point, 50.0, 1.0)
        p2 = project_onto_half_plane(p1, 50.0, 1.0)
        assert jnp.allclose(p1, p2, atol=1e-6)


# ---------------------------------------------------------------------------
# project_onto_edge_strip
# ---------------------------------------------------------------------------


class TestProjectOntoEdgeStrip:
    BOARD_W = 100.0
    BOARD_H = 100.0
    MAX_DIST = 20.0

    def test_bottom_edge_inside_strip(self):
        """Point inside bottom strip identity."""
        result = project_onto_edge_strip(
            jnp.array([50.0, 10.0]), self.BOARD_W, self.BOARD_H, self.MAX_DIST, "bottom"
        )
        assert jnp.allclose(result, jnp.array([50.0, 10.0]))

    def test_center_clamped_to_bottom_strip(self):
        """Point at center clamped to bottom edge strip."""
        result = project_onto_edge_strip(
            jnp.array([50.0, 50.0]), self.BOARD_W, self.BOARD_H, self.MAX_DIST, "bottom"
        )
        assert jnp.allclose(result, jnp.array([50.0, 20.0]))

    def test_top_edge_center_clamped(self):
        """Point at center clamped to top edge strip."""
        result = project_onto_edge_strip(
            jnp.array([50.0, 50.0]), self.BOARD_W, self.BOARD_H, self.MAX_DIST, "top"
        )
        assert jnp.allclose(result, jnp.array([50.0, 80.0]))

    def test_left_edge_clamped(self):
        """Point far right clamped to left."""
        result = project_onto_edge_strip(
            jnp.array([90.0, 50.0]), self.BOARD_W, self.BOARD_H, self.MAX_DIST, "left"
        )
        assert jnp.allclose(result, jnp.array([20.0, 50.0]))

    def test_right_edge_clamped(self):
        """Point far left clamped to right."""
        result = project_onto_edge_strip(
            jnp.array([10.0, 50.0]), self.BOARD_W, self.BOARD_H, self.MAX_DIST, "right"
        )
        assert jnp.allclose(result, jnp.array([80.0, 50.0]))

    def test_invalid_edge_raises(self):
        """Invalid edge identifier raises ValueError."""
        with pytest.raises(ValueError, match="Invalid edge"):
            project_onto_edge_strip(
                jnp.array([50.0, 50.0]), self.BOARD_W, self.BOARD_H, self.MAX_DIST, "north"
            )

    @pytest.mark.parametrize("edge", ["left", "right", "top", "bottom"])
    def test_idempotent(self, edge):
        """P(P(x)) == P(x)."""
        point = jnp.array([20.0, 20.0])
        p1 = project_onto_edge_strip(point, self.BOARD_W, self.BOARD_H, self.MAX_DIST, edge)
        p2 = project_onto_edge_strip(p1, self.BOARD_W, self.BOARD_H, self.MAX_DIST, edge)
        assert jnp.allclose(p1, p2, atol=1e-6)


# ---------------------------------------------------------------------------
# project_onto_side
# ---------------------------------------------------------------------------


class TestProjectOntoSide:
    BOARD_H = 100.0
    MIDLINE = 50.0

    def test_top_side_above_midline_clamped(self):
        """Above midline, top, clamped to midline."""
        result = project_onto_side(jnp.array([50.0, 70.0]), self.BOARD_H, self.MIDLINE, "top")
        assert jnp.allclose(result, jnp.array([50.0, 50.0]))

    def test_top_side_below_midline_identity(self):
        """Below midline, top, unchanged."""
        result = project_onto_side(jnp.array([50.0, 30.0]), self.BOARD_H, self.MIDLINE, "top")
        assert jnp.allclose(result, jnp.array([50.0, 30.0]))

    def test_bottom_side_below_midline_clamped(self):
        """Below midline, bottom, clamped."""
        result = project_onto_side(jnp.array([50.0, 30.0]), self.BOARD_H, self.MIDLINE, "bottom")
        assert jnp.allclose(result, jnp.array([50.0, 50.0]))

    def test_bottom_side_above_midline_identity(self):
        """Above midline, bottom, unchanged."""
        result = project_onto_side(jnp.array([50.0, 70.0]), self.BOARD_H, self.MIDLINE, "bottom")
        assert jnp.allclose(result, jnp.array([50.0, 70.0]))

    def test_invalid_side_raises(self):
        """Invalid side identifier raises ValueError."""
        with pytest.raises(ValueError, match="Invalid side"):
            project_onto_side(jnp.array([50.0, 50.0]), self.BOARD_H, self.MIDLINE, "both")

    @pytest.mark.parametrize("side", ["top", "bottom"])
    def test_idempotent(self, side):
        """P(P(x)) == P(x)."""
        point = jnp.array([50.0, 50.0])
        p1 = project_onto_side(point, self.BOARD_H, self.MIDLINE, side)
        p2 = project_onto_side(p1, self.BOARD_H, self.MIDLINE, side)
        assert jnp.allclose(p1, p2, atol=1e-6)


# ---------------------------------------------------------------------------
# identity_projection
# ---------------------------------------------------------------------------


class TestIdentityProjection:
    def test_returns_same_point(self):
        """Identity returns unchanged."""
        point = jnp.array([42.0, 73.0])
        assert jnp.all(identity_projection(point) == point)

    def test_idempotent(self):
        """I(I(x)) == I(x)."""
        point = jnp.array([1.0, 2.0])
        assert jnp.allclose(identity_projection(identity_projection(point)), identity_projection(point))
