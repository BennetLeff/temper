"""
Coverage-paydown tests for DRC inflate functions still uncovered.

Covered:
- precompute_from_pad_polygons (needs Shapely)
- inflate_pad_polygon (needs Shapely)
- precompute_inflated_dims (needs Shapely)

These functions require Shapely which is the sole dependency not migrated
to Rust. Tests are skipped if Shapely is not installed.
"""

import numpy as np
import pytest

try:
    from shapely.geometry import Polygon as ShapelyPolygon

    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not SHAPELY_AVAILABLE, reason="Shapely not installed"
)


class TestDRCInflateShapely:
    """Test DRC inflate functions that require Shapely."""

    def test_inflate_pad_polygon_simple(self):
        """Inflate a simple square pad polygon."""
        from temper_placer.geometry.drc_inflate import inflate_pad_polygon

        vertices = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
        min_x, min_y, max_x, max_y = inflate_pad_polygon(vertices, trace_width_mm=0.25)
        # Bounds should be expanded by trace_width/2 = 0.125 on each side
        assert min_x < 0.0
        assert min_y < 0.0
        assert max_x > 2.0
        assert max_y > 2.0
        # Should expand by approximately 0.125 each way
        assert np.isclose(min_x, -0.125, atol=0.01)

    def test_inflate_pad_polygon_rectangular(self):
        """Inflate a rectangular pad."""
        from temper_placer.geometry.drc_inflate import inflate_pad_polygon

        vertices = [(1.0, 2.0), (5.0, 2.0), (5.0, 3.5), (1.0, 3.5)]
        min_x, min_y, max_x, max_y = inflate_pad_polygon(vertices, trace_width_mm=0.4)
        # trace_width_mm=0.4 -> buffer radius = 0.2
        assert np.isclose(min_x, 0.8, atol=0.01)
        assert np.isclose(min_y, 1.8, atol=0.01)
        assert np.isclose(max_x, 5.2, atol=0.01)
        assert np.isclose(max_y, 3.7, atol=0.01)

    def test_precompute_inflated_dims_single(self):
        """Precompute inflated dims for a single pad polygon."""
        from temper_placer.geometry.drc_inflate import precompute_inflated_dims

        pad_vertices_list = [[(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]]
        result = precompute_inflated_dims(pad_vertices_list, trace_width_mm=0.25)
        assert isinstance(result, np.ndarray)
        assert result.shape == (1, 2)
        # Width/height inflated by 0.25: 2.0 + 0.25 = 2.25
        assert np.isclose(result[0, 0], 2.25, atol=0.01)
        assert np.isclose(result[0, 1], 2.25, atol=0.01)

    def test_precompute_inflated_dims_multiple(self):
        """Precompute inflated dims for multiple pad polygons."""
        from temper_placer.geometry.drc_inflate import precompute_inflated_dims

        pad_vertices_list = [
            [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)],
            [(0.0, 0.0), (3.0, 0.0), (3.0, 1.5), (0.0, 1.5)],
        ]
        result = precompute_inflated_dims(pad_vertices_list, trace_width_mm=0.25)
        assert result.shape == (2, 2)
        assert np.isclose(result[0, 0], 2.25, atol=0.01)
        assert np.isclose(result[0, 1], 2.25, atol=0.01)
        assert np.isclose(result[1, 0], 3.25, atol=0.01)
        assert np.isclose(result[1, 1], 1.75, atol=0.01)

    def test_precompute_inflated_dims_empty_pad(self):
        """Empty pad vertices yield zero dimensions."""
        from temper_placer.geometry.drc_inflate import precompute_inflated_dims

        pad_vertices_list = [[(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)], []]
        result = precompute_inflated_dims(pad_vertices_list, trace_width_mm=0.25)
        assert result.shape == (2, 2)
        assert np.isclose(result[1, 0], 0.0)
        assert np.isclose(result[1, 1], 0.0)

    def test_precompute_inflated_dims_empty_list(self):
        """Empty input list yields (0, 2) array."""
        from temper_placer.geometry.drc_inflate import precompute_inflated_dims

        result = precompute_inflated_dims([], trace_width_mm=0.25)
        assert isinstance(result, np.ndarray)
        assert result.shape == (0, 2)

    def test_precompute_from_pad_polygons_single(self):
        """Precompute from Shapely Polygon objects."""
        from temper_placer.geometry.drc_inflate import precompute_from_pad_polygons

        poly = ShapelyPolygon([(0, 0), (2, 0), (2, 2), (0, 2)])
        result = precompute_from_pad_polygons([poly], trace_width_mm=0.25)
        assert isinstance(result, np.ndarray)
        assert result.shape == (1, 2)
        assert np.isclose(result[0, 0], 2.25, atol=0.01)
        assert np.isclose(result[0, 1], 2.25, atol=0.01)

    def test_precompute_from_pad_polygons_multiple(self):
        """Precompute from multiple Shapely Polygon objects."""
        from temper_placer.geometry.drc_inflate import precompute_from_pad_polygons

        poly1 = ShapelyPolygon([(0, 0), (2, 0), (2, 2), (0, 2)])
        poly2 = ShapelyPolygon([(0, 0), (3, 0), (3, 1.5), (0, 1.5)])
        result = precompute_from_pad_polygons([poly1, poly2], trace_width_mm=0.25)
        assert result.shape == (2, 2)
        assert np.isclose(result[1, 0], 3.25, atol=0.01)
        assert np.isclose(result[1, 1], 1.75, atol=0.01)

    def test_precompute_from_pad_polygons_empty(self):
        """Precompute from empty list of Polygons."""
        from temper_placer.geometry.drc_inflate import precompute_from_pad_polygons

        result = precompute_from_pad_polygons([], trace_width_mm=0.25)
        assert isinstance(result, np.ndarray)
        # Empty list produces (0,) shaped array (np.array([], dtype=float32))
        assert result.shape[0] == 0

    def test_precompute_from_pad_polygons_empty_polygon(self):
        """Empty Shapely Polygon yields zero dimensions."""
        from temper_placer.geometry.drc_inflate import precompute_from_pad_polygons

        empty_poly = ShapelyPolygon()
        result = precompute_from_pad_polygons([empty_poly], trace_width_mm=0.25)
        assert result.shape == (1, 2)
        assert np.isclose(result[0, 0], 0.0)
        assert np.isclose(result[0, 1], 0.0)
