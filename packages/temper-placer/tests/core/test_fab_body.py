"""Tests for core.fab_body module.

Mirrors ``tests/core/test_courtyard.py``'s coverage (both classes delegate
to the identical ``temper_geometry.courtyard_global_points_py`` kernel) plus
the ``FabBody``-specific "no fabricated fallback shape" contract: a
component with no parsed F.Fab geometry must never silently behave as if it
had zero extent (that could either manufacture a false collision against a
neighbor, or -- worse -- mask a real one).
"""

from __future__ import annotations

import pytest

from temper_placer.core.fab_body import FabBody


class TestFabBody:
    def test_create_with_points(self):
        points = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        body = FabBody(component_ref="C1", points=points)
        assert body.component_ref == "C1"
        assert body.has_geometry

    def test_few_points_has_no_geometry(self):
        """Unlike Courtyard, FabBody does NOT fall back to a small box for
        <3 points -- see the module docstring: a fabricated body shape is
        never appropriate for a collision guard."""
        body = FabBody(component_ref="C1", points=[(0.0, 0.0), (1.0, 1.0)])
        assert body.points == []
        assert not body.has_geometry

    def test_get_global_polygon_no_rotation(self):
        points = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        body = FabBody(component_ref="C1", points=points)
        poly = body.get_global_polygon(x=10.0, y=20.0, rotation_idx=0)
        bounds = poly.bounds
        assert bounds == pytest.approx((9.0, 19.0, 11.0, 21.0))

    def test_get_global_polygon_90_rotation(self):
        # Same fixture/expected bounds as test_courtyard.py's equivalent
        # case -- proves FabBody uses the identical canonical rotation
        # kernel, not independently re-derived arithmetic.
        points = [(-1.0, -1.0), (2.0, -1.0), (2.0, 1.0), (-1.0, 1.0)]
        body = FabBody(component_ref="C1", points=points)
        poly = body.get_global_polygon(x=0.0, y=0.0, rotation_idx=1)
        bounds = poly.bounds
        assert bounds == pytest.approx((-1.0, -2.0, 1.0, 1.0))

    def test_offset_body_rotation_matches_measured_board_reproduction(self):
        """Reproduces the C2/C3 world-body-center numbers independently
        measured against the live board and cross-validated against PR
        #1158's separate parser (see body_collision.py module docstring):
        C2's F.Fab circle is centered at local (5, 0) with the footprint at
        board position (93.48, 64.84), rotation_idx 0 -> world center
        (98.48, 64.84); C3 at (87.36, 34.94), rotation_idx 3 (270deg) ->
        world center (87.36, 39.94)."""
        tiny_tri = [(5.0 - 0.001, -0.001), (5.0 + 0.002, 0.0), (5.0 - 0.001, 0.001)]

        c2 = FabBody(component_ref="C2", points=tiny_tri)
        poly = c2.get_global_polygon(x=93.48, y=64.84, rotation_idx=0)
        cx, cy = poly.centroid.coords[0]
        assert (cx, cy) == pytest.approx((98.48, 64.84), abs=1e-9)

        c3 = FabBody(component_ref="C3", points=tiny_tri)
        poly = c3.get_global_polygon(x=87.36, y=34.94, rotation_idx=3)
        cx, cy = poly.centroid.coords[0]
        assert (cx, cy) == pytest.approx((87.36, 39.94), abs=1e-9)

    def test_get_global_polygon_raises_without_geometry(self):
        body = FabBody(component_ref="C1", points=[])
        with pytest.raises(ValueError, match="no parsed F.Fab geometry"):
            body.get_global_polygon(0.0, 0.0, 0)
