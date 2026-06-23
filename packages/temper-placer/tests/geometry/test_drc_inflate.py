"""Unit tests for DRC inflation geometry utilities."""
import numpy as np
import jax.numpy as jnp
import pytest

from temper_placer.geometry.drc_inflate import (
    inflate_pad_polygon,
    precompute_inflated_dims,
    compute_inflated_half_dims_from_bounds,
    compute_drc_proxy_score,
)


def _has_shapely():
    try:
        import shapely
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_shapely(), reason="shapely not installed")
class TestInflatePadPolygon:
    def test_simple_rect(self):
        """Inflation of a simple rectangle increases bounds."""
        pad = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]
        min_x, min_y, max_x, max_y = inflate_pad_polygon(pad, trace_width_mm=0.25)

        assert min_x < 0.0
        assert min_y < 0.0
        assert max_x > 10.0
        assert max_y > 5.0

    def test_inflation_proportional_to_trace_width(self):
        """Larger trace width produces larger inflation."""
        pad = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]

        r1 = inflate_pad_polygon(pad, trace_width_mm=0.25)
        r2 = inflate_pad_polygon(pad, trace_width_mm=1.0)

        w1 = r1[2] - r1[0]
        w2 = r2[2] - r2[0]
        assert w2 > w1


@pytest.mark.skipif(not _has_shapely(), reason="shapely not installed")
class TestPrecomputeInflatedDims:
    def test_returns_correct_shape(self):
        """Precomputed dims have correct shape (N, 2)."""
        pad_list = [
            [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
            [(0.0, 0.0), (8.0, 0.0), (8.0, 4.0), (0.0, 4.0)],
            [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0)],
        ]
        result = precompute_inflated_dims(pad_list, trace_width_mm=0.25)
        assert result.shape == (3, 2)
        assert result.dtype == np.float32

    def test_empty_pad_list(self):
        """Empty pad list returns NaN-safe zeros."""
        result = precompute_inflated_dims([], trace_width_mm=0.25)
        assert result.shape == (0, 2)

    def test_empty_pad_vertices(self):
        """Empty pad vertices return zero dims."""
        result = precompute_inflated_dims([[]], trace_width_mm=0.25)
        assert result.shape == (1, 2)
        assert np.all(result == 0.0)


class TestComputeInflatedHalfDims:
    def test_inflation_adds_trace_width(self):
        """Half dims include trace_width inflation."""
        bounds = np.array([[10.0, 5.0], [8.0, 4.0]], dtype=np.float32)
        result = compute_inflated_half_dims_from_bounds(bounds, trace_width_mm=0.25)

        expected_hw1 = (10.0 + 0.25) / 2.0
        expected_hh1 = (5.0 + 0.25) / 2.0

        assert result.shape == (2, 2)
        assert abs(float(result[0, 0]) - expected_hw1) < 1e-6
        assert abs(float(result[0, 1]) - expected_hh1) < 1e-6


class TestComputeDRCProxyScore:
    def test_no_components(self):
        """Zero components give zero score."""
        positions = jnp.zeros((0, 2), dtype=jnp.float32)
        hw = jnp.zeros((0,), dtype=jnp.float32)
        hh = jnp.zeros((0,), dtype=jnp.float32)
        score = compute_drc_proxy_score(positions, hw, hh)
        assert float(score) == 0.0

    def test_separated_components(self):
        """Well-separated components produce low score."""
        n = 3
        hw = jnp.ones(n, dtype=jnp.float32) * 3.0
        hh = jnp.ones(n, dtype=jnp.float32) * 3.0
        positions = jnp.array([
            [0.0, 0.0],
            [100.0, 0.0],
            [200.0, 0.0],
        ], dtype=jnp.float32)
        score = compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2)
        assert float(score) < 1e-3

    def test_overlapping_components(self):
        """Overlapping inflated components produce positive score."""
        n = 2
        hw = jnp.array([5.0, 5.0], dtype=jnp.float32)
        hh = jnp.array([5.0, 5.0], dtype=jnp.float32)
        positions = jnp.array([
            [0.0, 0.0],
            [2.0, 0.0],
        ], dtype=jnp.float32)
        score = compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2)
        assert float(score) > 0.0

    def test_single_component(self):
        """Single component produces zero score."""
        hw = jnp.array([5.0], dtype=jnp.float32)
        hh = jnp.array([5.0], dtype=jnp.float32)
        positions = jnp.array([[0.0, 0.0]], dtype=jnp.float32)
        score = compute_drc_proxy_score(positions, hw, hh)
        assert float(score) == 0.0
