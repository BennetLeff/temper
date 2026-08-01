"""Unit tests for DRC inflation geometry utilities."""

import numpy as np
import pytest

from temper_placer.geometry.drc_inflate import (
    _smooth_relu_array,
    compute_drc_proxy_score,
    compute_inflated_half_dims_from_bounds,
    inflate_pad_polygon,
    precompute_inflated_dims,
)
from temper_placer.geometry.smooth import smooth_relu


def _has_shapely():
    try:
        import shapely  # noqa: F401  # side-effect import for availability check

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


class TestSmoothReluArray:
    """Vectorized smooth_relu must reproduce the scalar Rust math exactly."""

    @pytest.mark.parametrize(
        "x",
        [
            0.0,
            5.0,
            -5.0,
            0.001,
            -0.001,
            50.0,
            -50.0,
        ],
    )
    def test_matches_scalar_rust(self, x):
        """Array formulation equals the scalar temper_geometry binding."""
        expected = smooth_relu(x, alpha=10.0)
        result = _smooth_relu_array(np.array([x]), alpha=10.0)
        assert result.shape == (1,)
        assert abs(float(result[0]) - expected) < 1e-12

    def test_matches_scalar_rust_elementwise(self):
        """Sweep across the transition zone and extremes."""
        xs = np.concatenate(
            [
                np.linspace(-1.0, 1.0, 101),
                np.array([-1000.0, -100.0, 100.0, 1000.0]),
            ]
        )
        expected = np.array([smooth_relu(float(v), alpha=10.0) for v in xs])
        result = _smooth_relu_array(xs, alpha=10.0)
        assert np.allclose(result, expected, rtol=1e-9, atol=1e-12)

    def test_matches_scalar_rust_other_alpha(self):
        """Agreement holds for non-default alpha too."""
        xs = np.linspace(-2.0, 2.0, 41)
        expected = np.array([smooth_relu(float(v), alpha=3.0) for v in xs])
        result = _smooth_relu_array(xs, alpha=3.0)
        assert np.allclose(result, expected, rtol=1e-9, atol=1e-12)


class TestComputeDRCProxyScore:
    def test_no_components(self):
        """Zero components give zero score."""
        positions = np.zeros((0, 2), dtype=np.float32)
        hw = np.zeros((0,), dtype=np.float32)
        hh = np.zeros((0,), dtype=np.float32)
        score = compute_drc_proxy_score(positions, hw, hh)
        assert float(score) == 0.0

    def test_separated_components(self):
        """Well-separated components produce low score."""
        n = 3
        hw = np.ones(n, dtype=np.float32) * 3.0
        hh = np.ones(n, dtype=np.float32) * 3.0
        positions = np.array(
            [
                [0.0, 0.0],
                [100.0, 0.0],
                [200.0, 0.0],
            ],
            dtype=np.float32,
        )
        score = compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2)
        assert float(score) < 1e-3

    def test_overlapping_components(self):
        """Overlapping inflated components produce positive score."""
        hw = np.array([5.0, 5.0], dtype=np.float32)
        hh = np.array([5.0, 5.0], dtype=np.float32)
        positions = np.array(
            [
                [0.0, 0.0],
                [2.0, 0.0],
            ],
            dtype=np.float32,
        )
        score = compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2)
        assert float(score) > 0.0

    def test_single_component(self):
        """Single component produces zero score."""
        hw = np.array([5.0], dtype=np.float32)
        hh = np.array([5.0], dtype=np.float32)
        positions = np.array([[0.0, 0.0]], dtype=np.float32)
        score = compute_drc_proxy_score(positions, hw, hh)
        assert float(score) == 0.0

    @staticmethod
    def _reference_score(positions, hw, hh, clearance_mm, beta):
        """Ground-truth score using the scalar Rust smooth_relu in a loop."""
        n = positions.shape[0]
        total = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                gap_x = abs(positions[i, 0] - positions[j, 0]) - (hw[i] + hw[j])
                gap_y = abs(positions[i, 1] - positions[j, 1]) - (hh[i] + hh[j])
                dist = (
                    min(gap_x, gap_y) if gap_x < 0.0 and gap_y < 0.0 else max(gap_x, gap_y)
                )
                v = smooth_relu(clearance_mm - dist, alpha=beta)
                total += v * v
        return total

    @pytest.mark.parametrize("n", [2, 3, 5])
    def test_matches_scalar_reference(self, n):
        """Multi-component array path equals the scalar-loop reference."""
        rng = np.random.default_rng(42)
        positions = rng.uniform(-20.0, 20.0, size=(n, 2)).astype(np.float32)
        hw = rng.uniform(0.5, 4.0, size=(n,)).astype(np.float32)
        hh = rng.uniform(0.5, 4.0, size=(n,)).astype(np.float32)
        score = compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2, beta=10.0)
        expected = self._reference_score(positions, hw, hh, clearance_mm=0.2, beta=10.0)
        assert abs(float(score) - expected) < 1e-6
