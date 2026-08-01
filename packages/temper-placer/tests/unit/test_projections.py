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

All operators delegate to the temper_geometry Rust crate; the Python
wrappers in `temper_placer.geometry.projections` take flat scalar
coordinates and return (x, y) tuples.
"""

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
    # Zone rect: origin (0, 0), size (10, 10)
    ZX, ZY, ZW, ZH = 0.0, 0.0, 10.0, 10.0

    def test_inside_rect_identity(self):
        """Point inside rect zone returns unchanged."""
        result = project_onto_zone(5.0, 5.0, self.ZX, self.ZY, self.ZW, self.ZH)
        assert result == (5.0, 5.0)

    def test_outside_left_clamped(self):
        """Point left of rect clamped to left edge."""
        result = project_onto_zone(-5.0, 5.0, self.ZX, self.ZY, self.ZW, self.ZH)
        assert result == (0.0, 5.0)

    def test_outside_right_clamped(self):
        """Point right of rect clamped to right edge."""
        result = project_onto_zone(15.0, 5.0, self.ZX, self.ZY, self.ZW, self.ZH)
        assert result == (10.0, 5.0)

    def test_outside_top_clamped(self):
        """Point above rect clamped to top edge."""
        result = project_onto_zone(5.0, 15.0, self.ZX, self.ZY, self.ZW, self.ZH)
        assert result == (5.0, 10.0)

    def test_outside_bottom_clamped(self):
        """Point below rect clamped to bottom edge."""
        result = project_onto_zone(5.0, -5.0, self.ZX, self.ZY, self.ZW, self.ZH)
        assert result == (5.0, 0.0)

    @pytest.mark.parametrize(
        "point",
        [
            (3.0, 3.0),
            (8.0, 8.0),
            (5.0, 5.0),
        ],
    )
    def test_idempotent(self, point):
        """P(P(x)) == P(x) for convex zone."""
        px, py = point
        p1 = project_onto_zone(px, py, self.ZX, self.ZY, self.ZW, self.ZH)
        p2 = project_onto_zone(*p1, self.ZX, self.ZY, self.ZW, self.ZH)
        assert p1 == pytest.approx(p2, abs=1e-6)


# ---------------------------------------------------------------------------
# project_outside_keepout
# ---------------------------------------------------------------------------


class TestProjectOutsideKeepout:
    KEEPOUT = (5.0, 5.0, 10.0, 10.0)

    def test_outside_keepout_identity(self):
        """Point outside keepout returns unchanged."""
        kx, ky, kw, kh = self.KEEPOUT
        result = project_outside_keepout(1.0, 1.0, kx, ky, kw, kh)
        assert result == (1.0, 1.0)

    def test_inside_keepout_projected(self):
        """Point inside keepout projected to nearest edge."""
        kx, ky, kw, kh = self.KEEPOUT
        result = project_outside_keepout(7.5, 7.5, kx, ky, kw, kh)
        # Nearest edge from center (7.5, 7.5) is left at x=5
        assert result == (5.0, 7.5)

    def test_on_keepout_edge_stays_on_edge(self):
        """Point on keepout boundary maps to that boundary point."""
        kx, ky, kw, kh = self.KEEPOUT
        result = project_outside_keepout(5.0, 7.5, kx, ky, kw, kh)
        # Boundary is inclusive; the nearest candidate is the point itself.
        assert result == (5.0, 7.5)

    def test_with_half_size_expands_keepout(self):
        """Half-size expands keepout outward."""
        kx, ky, kw, kh = self.KEEPOUT
        result = project_outside_keepout(8.0, 8.0, kx, ky, kw, kh, half_w=3.0, half_h=3.0)
        # Expanded keepout x ∈ [2, 18], y ∈ [2, 18]; (8, 8) is inside.
        # Nearest edges are left (2, 8) and bottom (8, 2), both at distance 6.
        # argmin with ties picks first, so left edge.
        assert result == (2.0, 8.0)

    @pytest.mark.parametrize(
        "point",
        [
            (1.0, 1.0),
            (12.0, 12.0),
        ],
    )
    def test_idempotent(self, point):
        """P(P(x)) == P(x)."""
        kx, ky, kw, kh = self.KEEPOUT
        px, py = point
        p1 = project_outside_keepout(px, py, kx, ky, kw, kh)
        p2 = project_outside_keepout(*p1, kx, ky, kw, kh)
        assert p1 == pytest.approx(p2, abs=1e-6)


# ---------------------------------------------------------------------------
# project_onto_board
# ---------------------------------------------------------------------------


class TestProjectOntoBoard:
    BOARD_W = 100.0
    BOARD_H = 100.0
    MARGIN = 3.0

    def test_inside_identity(self):
        """Point inside board margins returns unchanged."""
        result = project_onto_board(50.0, 50.0, self.BOARD_W, self.BOARD_H, self.MARGIN)
        assert result == (50.0, 50.0)

    def test_below_left_corner_clamped(self):
        """Point below minimum x and y clamped."""
        result = project_onto_board(-1.0, -1.0, self.BOARD_W, self.BOARD_H, self.MARGIN)
        assert result == (3.0, 3.0)

    def test_above_right_corner_clamped(self):
        """Point above maximum x and y clamped."""
        result = project_onto_board(102.0, 105.0, self.BOARD_W, self.BOARD_H, self.MARGIN)
        assert result == (97.0, 97.0)

    @pytest.mark.parametrize(
        "point",
        [
            (10.0, 10.0),
            (90.0, 90.0),
        ],
    )
    def test_idempotent(self, point):
        """P(P(x)) == P(x)."""
        px, py = point
        p1 = project_onto_board(px, py, self.BOARD_W, self.BOARD_H, self.MARGIN)
        p2 = project_onto_board(*p1, self.BOARD_W, self.BOARD_H, self.MARGIN)
        assert p1 == pytest.approx(p2, abs=1e-6)


# ---------------------------------------------------------------------------
# project_onto_half_plane
# ---------------------------------------------------------------------------

# Half-plane: feasible set is {q | (q - origin) · normal >= 0}.
# HV side (y >= 20): origin (0, 20), normal (0, 1).
# LV side (y <= 20): origin (0, 20), normal (0, -1).


class TestProjectOntoHalfPlane:
    HV_ORIGIN = (0.0, 20.0)
    HV_NORMAL = (0.0, 1.0)
    LV_NORMAL = (0.0, -1.0)

    def test_hv_above_boundary_identity(self):
        """Point above boundary, HV normal, identity."""
        result = project_onto_half_plane(50.0, 30.0, *self.HV_ORIGIN, *self.HV_NORMAL)
        assert result == (50.0, 30.0)

    def test_hv_below_boundary_projected(self):
        """Point below boundary, HV normal, projected to boundary."""
        result = project_onto_half_plane(50.0, 10.0, *self.HV_ORIGIN, *self.HV_NORMAL)
        assert result == (50.0, 20.0)

    def test_lv_below_boundary_identity(self):
        """Point below boundary, LV normal, identity."""
        result = project_onto_half_plane(50.0, 10.0, *self.HV_ORIGIN, *self.LV_NORMAL)
        assert result == (50.0, 10.0)

    def test_lv_above_boundary_projected(self):
        """Point above boundary, LV normal, projected to boundary."""
        result = project_onto_half_plane(50.0, 30.0, *self.HV_ORIGIN, *self.LV_NORMAL)
        assert result == (50.0, 20.0)

    def test_degenerate_normal_is_noop(self):
        """Zero-length normal is treated as a no-op."""
        result = project_onto_half_plane(50.0, 10.0, 0.0, 20.0, 0.0, 0.0)
        assert result == (50.0, 10.0)

    @pytest.mark.parametrize(
        "point",
        [
            (10.0, 5.0),
            (80.0, 95.0),
        ],
    )
    def test_idempotent(self, point):
        """P(P(x)) == P(x) for convex half-plane."""
        px, py = point
        p1 = project_onto_half_plane(px, py, 0.0, 50.0, 0.0, 1.0)
        p2 = project_onto_half_plane(*p1, 0.0, 50.0, 0.0, 1.0)
        assert p1 == pytest.approx(p2, abs=1e-6)


# ---------------------------------------------------------------------------
# project_onto_edge_strip
# ---------------------------------------------------------------------------


class TestProjectOntoEdgeStrip:
    # Edge line segments (100 x 100 board):
    #   bottom: (0, 0) -> (100, 0),  top: (0, 100) -> (100, 100)
    #   left:   (0, 0) -> (0, 100),  right: (100, 0) -> (100, 100)
    EDGES = {
        "bottom": (0.0, 0.0, 100.0, 0.0),
        "top": (0.0, 100.0, 100.0, 100.0),
        "left": (0.0, 0.0, 0.0, 100.0),
        "right": (100.0, 0.0, 100.0, 100.0),
    }
    STRIP_WIDTH = 20.0

    def test_bottom_edge_inside_strip(self):
        """Point inside bottom strip identity."""
        result = project_onto_edge_strip(50.0, 10.0, *self.EDGES["bottom"], self.STRIP_WIDTH)
        assert result == (50.0, 10.0)

    def test_center_clamped_to_bottom_strip(self):
        """Point at center clamped to bottom edge strip."""
        result = project_onto_edge_strip(50.0, 50.0, *self.EDGES["bottom"], self.STRIP_WIDTH)
        assert result == (50.0, 20.0)

    def test_top_edge_center_clamped(self):
        """Point at center clamped to top edge strip."""
        result = project_onto_edge_strip(50.0, 50.0, *self.EDGES["top"], self.STRIP_WIDTH)
        assert result == (50.0, 80.0)

    def test_left_edge_clamped(self):
        """Point far right clamped to left."""
        result = project_onto_edge_strip(90.0, 50.0, *self.EDGES["left"], self.STRIP_WIDTH)
        assert result == (20.0, 50.0)

    def test_right_edge_clamped(self):
        """Point far left clamped to right."""
        result = project_onto_edge_strip(10.0, 50.0, *self.EDGES["right"], self.STRIP_WIDTH)
        assert result == (80.0, 50.0)

    @pytest.mark.parametrize("edge", ["left", "right", "top", "bottom"])
    def test_idempotent(self, edge):
        """P(P(x)) == P(x)."""
        p1 = project_onto_edge_strip(20.0, 20.0, *self.EDGES[edge], self.STRIP_WIDTH)
        p2 = project_onto_edge_strip(*p1, *self.EDGES[edge], self.STRIP_WIDTH)
        assert p1 == pytest.approx(p2, abs=1e-6)


# ---------------------------------------------------------------------------
# project_onto_side
# ---------------------------------------------------------------------------


class TestProjectOntoSide:
    BOARD_W = 100.0
    BOARD_H = 100.0

    def test_top_side_above_midline_clamped(self):
        """Above midline, top, clamped to midline."""
        result = project_onto_side(50.0, 70.0, self.BOARD_W, self.BOARD_H, "top")
        assert result == (50.0, 50.0)

    def test_top_side_below_midline_identity(self):
        """Below midline, top, unchanged."""
        result = project_onto_side(50.0, 30.0, self.BOARD_W, self.BOARD_H, "top")
        assert result == (50.0, 30.0)

    def test_bottom_side_below_midline_clamped(self):
        """Below midline, bottom, clamped."""
        result = project_onto_side(50.0, 30.0, self.BOARD_W, self.BOARD_H, "bottom")
        assert result == (50.0, 50.0)

    def test_bottom_side_above_midline_identity(self):
        """Above midline, bottom, unchanged."""
        result = project_onto_side(50.0, 70.0, self.BOARD_W, self.BOARD_H, "bottom")
        assert result == (50.0, 70.0)

    def test_invalid_side_raises(self):
        """Invalid side identifier raises RuntimeError (Rust panic)."""
        with pytest.raises(RuntimeError, match="Invalid side"):
            project_onto_side(50.0, 50.0, self.BOARD_W, self.BOARD_H, "both")

    @pytest.mark.parametrize("side", ["top", "bottom"])
    def test_idempotent(self, side):
        """P(P(x)) == P(x)."""
        p1 = project_onto_side(50.0, 50.0, self.BOARD_W, self.BOARD_H, side)
        p2 = project_onto_side(*p1, self.BOARD_W, self.BOARD_H, side)
        assert p1 == pytest.approx(p2, abs=1e-6)


# ---------------------------------------------------------------------------
# identity_projection
# ---------------------------------------------------------------------------


class TestIdentityProjection:
    def test_returns_same_point(self):
        """Identity returns unchanged."""
        assert identity_projection(42.0, 73.0) == (42.0, 73.0)

    def test_idempotent(self):
        """I(I(x)) == I(x)."""
        p1 = identity_projection(1.0, 2.0)
        p2 = identity_projection(*p1)
        assert p1 == p2
