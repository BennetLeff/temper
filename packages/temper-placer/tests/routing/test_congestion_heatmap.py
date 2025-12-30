"""Tests for congestion heatmap.

Part of temper-gzur.1
"""

import numpy as np
import pytest


class TestCongestionHeatmap:
    """Tests for CongestionHeatmap."""

    def test_get_congestion_at(self):
        """Query returns valid congestion values."""
        from temper_placer.routing.congestion_heatmap import CongestionHeatmap
        
        grid = np.array([[0.0, 0.5], [0.2, 1.0]], dtype=np.float32)
        heatmap = CongestionHeatmap(grid=grid, cell_size=1.0, origin=(0, 0))
        
        assert heatmap.get_congestion_at(0, 0) == pytest.approx(0.0)
        assert heatmap.get_congestion_at(1, 1) == pytest.approx(1.0)
        assert heatmap.get_congestion_at(0.5, 0.5) == pytest.approx(0.0)  # Rounds to (0,0)

    def test_get_total_congestion(self):
        """Total congestion sums grid."""
        from temper_placer.routing.congestion_heatmap import CongestionHeatmap
        
        grid = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
        heatmap = CongestionHeatmap(grid=grid, cell_size=1.0, origin=(0, 0))
        
        assert heatmap.get_total_congestion() == pytest.approx(1.0)

    def test_get_hotspots(self):
        """Hotspots returns high-congestion locations."""
        from temper_placer.routing.congestion_heatmap import CongestionHeatmap
        
        grid = np.array([[0.1, 0.9], [0.2, 0.8]], dtype=np.float32)
        heatmap = CongestionHeatmap(grid=grid, cell_size=1.0, origin=(0, 0))
        
        hotspots = heatmap.get_hotspots(threshold=0.5)
        
        assert len(hotspots) == 2  # (0,1) and (1,1)
        assert hotspots[0][2] == pytest.approx(0.9)  # Highest first

    def test_out_of_bounds_clamps(self):
        """Queries outside grid clamp to edge."""
        from temper_placer.routing.congestion_heatmap import CongestionHeatmap
        
        grid = np.array([[0.5]], dtype=np.float32)
        heatmap = CongestionHeatmap(grid=grid, cell_size=1.0, origin=(0, 0))
        
        # Far outside grid
        assert heatmap.get_congestion_at(100, 100) == pytest.approx(0.5)
        assert heatmap.get_congestion_at(-100, -100) == pytest.approx(0.5)
