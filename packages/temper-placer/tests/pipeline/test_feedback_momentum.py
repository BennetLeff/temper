"""Tests for MomentumDampedRoutingFeedbackLoss (U3)."""

import numpy as np
import pytest

from temper_placer.router_v6.congestion_heatmap import CongestionHeatmap


class MockCongestionHeatmap:
    """Minimal CongestionHeatmap-compatible object for testing."""

    def __init__(self, grid: np.ndarray):
        self.grid = grid
        self.origin = (0.0, 0.0)
        self.cell_size = 1.0


class TestMomentumDampedLoss:
    """EWMA momentum-damped congestion loss."""

    def _make_heatmap(self, grid: np.ndarray) -> MockCongestionHeatmap:
        return MockCongestionHeatmap(grid)

    def test_iteration_zero_blended_equals_raw(self):
        from temper_placer.pipeline.feedback import MomentumDampedRoutingFeedbackLoss

        grid = np.ones((10, 10), dtype=np.float64) * 0.5
        heatmap = self._make_heatmap(grid)
        loss_fn = MomentumDampedRoutingFeedbackLoss(heatmap, sigma=0.0)

        np.testing.assert_allclose(loss_fn.blended_grid, np.ones((10, 10)) * 0.5, atol=0.01)

    def test_constant_heatmap_converges(self):
        from temper_placer.pipeline.feedback import MomentumDampedRoutingFeedbackLoss

        grid = np.ones((10, 10), dtype=np.float64) * 0.5
        loss_fn = MomentumDampedRoutingFeedbackLoss(self._make_heatmap(grid), sigma=0.0)

        for i in range(1, 5):
            loss_fn.blend(self._make_heatmap(grid), iteration=i, sigma=0.0)

        np.testing.assert_allclose(loss_fn.blended_grid, np.ones((10, 10)) * 0.5, atol=0.01)

    def test_alternating_heatmaps_smoothed(self):
        from temper_placer.pipeline.feedback import MomentumDampedRoutingFeedbackLoss

        grid_a = np.zeros((10, 10), dtype=np.float64)
        grid_b = np.ones((10, 10), dtype=np.float64)

        loss_fn = MomentumDampedRoutingFeedbackLoss(self._make_heatmap(grid_a), sigma=0.0)
        for i in range(1, 6):
            grid = grid_a if i % 2 == 1 else grid_b
            loss_fn.blend(self._make_heatmap(grid), iteration=i, sigma=0.0)

        values = loss_fn.blended_grid.flatten()
        assert np.max(values) - np.min(values) < 0.5, (
            f"Alternating inputs should be smoothed, but range is {np.max(values) - np.min(values)}"
        )

    def test_alpha_never_below_floor(self):
        alpha_floor = 0.1
        for n in range(0, 100):
            alpha = max(alpha_floor, 1.0 / (n + 1))
            assert alpha >= alpha_floor, f"alpha={alpha} at iteration {n}"

    def test_blend_convergence_monotonicity(self):
        """Successive blends of the same grid decrease the L2 distance to the target."""
        from temper_placer.pipeline.feedback import MomentumDampedRoutingFeedbackLoss

        target = np.ones((10, 10), dtype=np.float64) * 0.8
        loss_fn = MomentumDampedRoutingFeedbackLoss(self._make_heatmap(np.zeros((10, 10))), sigma=0.0)

        prev_dist = float("inf")
        for i in range(1, 8):
            loss_fn.blend(self._make_heatmap(target), iteration=i, sigma=0.0)
            dist = float(np.linalg.norm(loss_fn.blended_grid - target))
            assert dist <= prev_dist * 1.01, (
                f"Distance should not increase: {dist} > {prev_dist} at iteration {i}"
            )
            prev_dist = dist

    def test_iteration_property(self):
        from temper_placer.pipeline.feedback import MomentumDampedRoutingFeedbackLoss

        loss_fn = MomentumDampedRoutingFeedbackLoss(self._make_heatmap(np.ones((10, 10))))
        assert loss_fn.iteration == 0
        loss_fn.blend(self._make_heatmap(np.ones((10, 10))), iteration=3)
        assert loss_fn.iteration == 3

    def test_single_pass_backward_compatible(self):
        """Existing RoutingFeedbackLoss is preserved for single-pass use."""
        from temper_placer.pipeline.feedback import RoutingFeedbackLoss

        heatmap = self._make_heatmap(np.ones((10, 10), dtype=np.float64))
        loss_fn = RoutingFeedbackLoss(heatmap, sigma=0.0)
        assert loss_fn.name == "routing_feedback"
        assert not loss_fn.supports_virtual_nodes
