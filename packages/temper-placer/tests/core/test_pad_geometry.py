"""Tests for core.pad_geometry -- the shape-correct pad extent model.

These tests exist to prove the two hard properties the fix plan requires:

- R1: circle/oval/rect/roundrect are each modeled by their own geometry, not
  a single shape-agnostic circle.
- R2: the model never under-reports a pad's physical extent, in any
  direction, for any shape -- including the square-pad corner case the old
  ``max(width, height) / 2`` formula got wrong (worst measured case on the
  real board: an 8x8mm rect pad, corners 1.657mm outside that model).
- R3: rotation is honoured (not assumed away), including non-axis-aligned
  rotation.
"""

import math

import pytest
from shapely.geometry import Point

from temper_placer.core.pad_geometry import (
    DEFAULT_ROUNDRECT_RATIO,
    pad_axis_radius,
    pad_bounding_radius,
    pad_core_half_extents,
    pad_corner_radius,
    pad_polygon,
    pad_support_radius,
)


class TestPadCornerRadius:
    def test_circle_uses_half_diameter(self):
        assert pad_corner_radius(8.0, 8.0, "circle") == pytest.approx(4.0)

    def test_thru_hole_aliases_circle(self):
        assert pad_corner_radius(2.0, 2.0, "thru_hole") == pad_corner_radius(2.0, 2.0, "circle")

    def test_oval_uses_half_of_shorter_dimension(self):
        assert pad_corner_radius(9.0, 4.8, "oval") == pytest.approx(2.4)

    def test_rect_has_zero_corner_radius(self):
        assert pad_corner_radius(8.0, 8.0, "rect") == 0.0

    def test_roundrect_uses_ratio_of_shorter_dimension(self):
        assert pad_corner_radius(2.0, 2.0, "roundrect", roundrect_ratio=0.25) == pytest.approx(0.5)

    def test_unrecognized_shape_falls_back_to_zero_conservatively(self, caplog):
        assert pad_corner_radius(5.0, 3.0, "custom") == 0.0


class TestSquarePadCornerCase:
    """The exact bug named in the plan: R30 pad 1, an 8x8mm rect pad."""

    def test_old_formula_under_reported_by_1_657mm(self):
        old_model_radius = max(8.0, 8.0) / 2.0
        true_corner_distance = math.hypot(4.0, 4.0)
        assert true_corner_distance - old_model_radius == pytest.approx(1.657, abs=0.001)

    def test_bounding_radius_covers_the_true_corner(self):
        r = pad_bounding_radius(8.0, 8.0, "rect")
        assert r == pytest.approx(math.hypot(4.0, 4.0))
        assert r > max(8.0, 8.0) / 2.0  # strictly bigger than the old (wrong) model

    def test_support_at_corner_direction_equals_bounding_radius(self):
        # The corner of an 8x8 rect sits at 45 degrees from center.
        support = pad_support_radius(8.0, 8.0, "rect", direction_rad=math.radians(45))
        assert support == pytest.approx(math.hypot(4.0, 4.0))


class TestElongatedPadShortAxis:
    """The other named bug: a 9x4.8mm pad over-reported to a 4.5mm radius
    where the true short-axis half-extent is 2.4mm."""

    def test_old_formula_over_reported_short_axis(self):
        old_model_radius = max(9.0, 4.8) / 2.0
        assert old_model_radius == pytest.approx(4.5)

    def test_axis_radius_short_axis_is_exact(self):
        # width=9 along local X, height=4.8 along local Y, unrotated.
        assert pad_axis_radius(9.0, 4.8, "rect", axis=1) == pytest.approx(2.4)
        assert pad_axis_radius(9.0, 4.8, "oval", axis=1) == pytest.approx(2.4)

    def test_axis_radius_long_axis_matches_half_width(self):
        assert pad_axis_radius(9.0, 4.8, "rect", axis=0) == pytest.approx(4.5)
        assert pad_axis_radius(9.0, 4.8, "oval", axis=0) == pytest.approx(4.5)

    def test_oval_bounding_radius_equals_old_formula_exactly(self):
        # A true stadium's furthest point IS exactly along its long axis --
        # this is the one shape where the old isotropic formula happens to
        # be the exact (not merely conservative) circumscribing radius.
        assert pad_bounding_radius(9.0, 4.8, "oval") == pytest.approx(4.5)


class TestAxisIndependentOfRoundrectRatio:
    """Along a pure local axis, the corner-rounding radius cancels out of
    the support formula entirely -- proven in the module docstring. This
    means an unknown/default roundrect_ratio can never distort an
    axis-aligned gap computation (the isolator feasibility check's own use
    case)."""

    @pytest.mark.parametrize("ratio", [0.0, 0.1, 0.25, 0.4, 0.5])
    def test_axis_radius_independent_of_ratio(self, ratio):
        r0 = pad_axis_radius(9.0, 4.8, "roundrect", axis=0, roundrect_ratio=ratio)
        r1 = pad_axis_radius(9.0, 4.8, "roundrect", axis=1, roundrect_ratio=ratio)
        assert r0 == pytest.approx(4.5)
        assert r1 == pytest.approx(2.4)


class TestRotation:
    def test_90deg_rotation_swaps_axes(self):
        r_x_unrot = pad_axis_radius(9.0, 4.8, "rect", axis=0, rotation_rad=0.0)
        r_x_rot90 = pad_axis_radius(9.0, 4.8, "rect", axis=0, rotation_rad=math.pi / 2)
        assert r_x_unrot == pytest.approx(4.5)
        assert r_x_rot90 == pytest.approx(2.4)

    def test_bounding_radius_is_rotation_invariant(self):
        unrot = pad_bounding_radius(8.0, 8.0, "roundrect", roundrect_ratio=0.3)
        for deg in (0, 17, 45, 90, 123, 270):
            # bounding_radius has no rotation parameter by construction;
            # cross-check that the sup over many sampled directions at a
            # rotated frame still matches it (rotation cannot raise the sup).
            rot = math.radians(deg)
            worst = max(
                pad_support_radius(8.0, 8.0, "roundrect", math.radians(a), rot, 0.3)
                for a in range(0, 360, 1)
            )
            assert worst == pytest.approx(unrot, abs=1e-6)

    def test_arbitrary_rotation_never_exceeds_bounding_radius(self):
        # Fuzz: for many shapes/rotations/directions, support() must never
        # exceed bounding_radius (R2's isotropic bound must hold everywhere).
        bound = pad_bounding_radius(9.0, 4.8, "roundrect", roundrect_ratio=0.25)
        for rot_deg in range(0, 360, 7):
            for dir_deg in range(0, 360, 5):
                s = pad_support_radius(
                    9.0, 4.8, "roundrect", math.radians(dir_deg), math.radians(rot_deg), 0.25
                )
                assert s <= bound + 1e-9


class TestNeverUnderReportsFuzz:
    """Broad property check across all four shapes: the bounding radius
    (used as a disk) must fully contain every point actually reachable by
    the pad's true boundary at any rotation, for a spread of aspect ratios."""

    SHAPES = ["circle", "oval", "rect", "roundrect"]

    @pytest.mark.parametrize("shape", SHAPES)
    @pytest.mark.parametrize("w,h", [(8.0, 8.0), (9.0, 4.8), (1.0, 5.0), (0.9, 0.95), (2.0, 2.0)])
    def test_support_function_never_exceeds_bounding_radius(self, shape, w, h):
        """The TRUE shape (via its exact support function, not the
        conservative circumscribing polygon) must never exceed
        pad_bounding_radius, at any rotation or query direction -- this is
        the actual R2 guarantee (see module docstring proof); the polygon
        from pad_polygon() is deliberately inflated slightly BEYOND this
        bound so it circumscribes the true arc (see
        TestPadPolygonCircumscribesTrueArc), so checking the polygon's own
        vertices against the exact bound is the wrong property to test."""
        if shape == "circle" and w != h:
            pytest.skip("circle pads are square by KiCad construction")
        bound = pad_bounding_radius(w, h, shape)
        for rot_deg in range(0, 360, 11):
            for dir_deg in range(0, 360, 7):
                s = pad_support_radius(
                    w, h, shape, math.radians(dir_deg), math.radians(rot_deg)
                )
                assert s <= bound + 1e-9, (
                    f"{shape} {w}x{h} rot={rot_deg} dir={dir_deg}: support "
                    f"{s} exceeds bounding radius {bound}"
                )

    @pytest.mark.parametrize("shape", SHAPES)
    @pytest.mark.parametrize("w,h", [(8.0, 8.0), (9.0, 4.8), (1.0, 5.0), (0.9, 0.95), (2.0, 2.0)])
    def test_polygon_circumscribes_bounding_disk(self, shape, w, h, quad_segs=16):
        """pad_polygon()'s vertices are allowed to sit slightly OUTSIDE the
        exact bounding radius (that is the point of the circumscribing
        inflation), but only by the explicit, provable slack the module
        docstring derives: r * (1/cos(pi/(2*quad_segs)) - 1)."""
        if shape == "circle" and w != h:
            pytest.skip("circle pads are square by KiCad construction")
        poly = pad_polygon(w, h, shape, cx=0.0, cy=0.0, rotation_rad=math.radians(23))
        bound = pad_bounding_radius(w, h, shape)
        r = pad_corner_radius(w, h, shape)
        slack = r * (1.0 / math.cos(math.pi / (2 * quad_segs)) - 1.0)
        for x, y in poly.exterior.coords:
            assert math.hypot(x, y) <= bound + slack + 1e-9, (
                f"{shape} {w}x{h}: polygon point ({x},{y}) at distance "
                f"{math.hypot(x, y)} exceeds bounding radius {bound} + "
                f"documented slack {slack}"
            )


class TestPadPolygonCircumscribesTrueArc:
    """pad_polygon()'s buffer-inflation must fully contain the true rounded
    shape -- i.e. never cut inside the true arc between sampled vertices."""

    def test_circle_polygon_contains_true_circle_samples(self):
        r = 3.0
        poly = pad_polygon(2 * r, 2 * r, "circle", cx=0.0, cy=0.0, quad_segs=8)
        for deg in range(0, 360, 1):
            a = math.radians(deg)
            true_point = Point(r * math.cos(a), r * math.sin(a))
            assert poly.contains(true_point) or poly.distance(true_point) < 1e-9

    def test_roundrect_polygon_contains_true_rounded_corner_samples(self):
        w, h, ratio = 8.0, 8.0, 0.25
        r = pad_corner_radius(w, h, "roundrect", ratio)
        hw, hh = pad_core_half_extents(w, h, "roundrect", ratio)
        poly = pad_polygon(w, h, "roundrect", cx=0.0, cy=0.0, quad_segs=8)
        # Sample the true rounded-corner arc (center of arc at (hw, hh),
        # sweeping from 0 to 90 degrees) at the top-right corner.
        for deg in range(0, 91, 2):
            a = math.radians(deg)
            true_point = Point(hw + r * math.cos(a), hh + r * math.sin(a))
            assert poly.contains(true_point) or poly.distance(true_point) < 1e-9

    def test_rect_polygon_is_exact_no_inflation_needed(self):
        poly = pad_polygon(9.0, 4.8, "rect", cx=0.0, cy=0.0)
        xs = [p[0] for p in poly.exterior.coords]
        ys = [p[1] for p in poly.exterior.coords]
        assert max(xs) == pytest.approx(4.5)
        assert max(ys) == pytest.approx(2.4)

    def test_rotated_polygon_translated_correctly(self):
        poly = pad_polygon(9.0, 4.8, "rect", cx=10.0, cy=20.0, rotation_rad=math.pi / 2)
        xs = [p[0] for p in poly.exterior.coords]
        ys = [p[1] for p in poly.exterior.coords]
        # After 90deg rotation, the long axis (was X) is now along Y.
        assert max(xs) - 10.0 == pytest.approx(2.4, abs=1e-6)
        assert max(ys) - 20.0 == pytest.approx(4.5, abs=1e-6)


class TestAxisValidation:
    def test_invalid_axis_raises(self):
        with pytest.raises(ValueError):
            pad_axis_radius(1.0, 1.0, "rect", axis=2)


class TestDefaultRatioConstant:
    def test_default_ratio_matches_kicad_default(self):
        assert DEFAULT_ROUNDRECT_RATIO == 0.25
