"""Tests for OccupancyManager and NetRouter classes."""

import numpy as np
import pytest

from temper_placer.routing.occupancy.manager import OccupancyManager
from temper_placer.routing.net_router import (
    NetRouter,
    NetRouterConfig,
    NetRouterResult,
    create_net_router,
)


class TestOccupancyManager:
    """Test cases for OccupancyManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = OccupancyManager(grid_size=(10, 10), num_layers=2)

    def test_initial_state(self):
        """Test that manager starts with all free cells."""
        stats = self.manager.get_stats()
        assert stats["free_cells"] == 200  # 10x10x2
        assert stats["blocked_cells"] == 0
        assert stats["routed_cells"] == 0

    def test_block_cells(self):
        """Test blocking cells."""
        cells = [(1, 1, 0), (2, 2, 0), (3, 3, 1)]
        self.manager.block_cells(cells)

        assert self.manager.is_blocked(1, 1, 0)
        assert self.manager.is_blocked(2, 2, 0)
        assert self.manager.is_blocked(3, 3, 1)
        assert not self.manager.is_blocked(0, 0, 0)

    def test_block_cells_with_net_name(self):
        """Test blocking cells with net ownership."""
        cells = [(1, 1, 0), (2, 2, 0)]
        self.manager.block_cells(cells, net_name="NetA")

        assert self.manager.get_cell_owner((1, 1, 0)) == "NetA"
        assert self.manager.get_cell_owner((2, 2, 0)) == "NetA"

    def test_unblock_cells(self):
        """Test unblocking cells."""
        cells = [(1, 1, 0), (2, 2, 0)]
        self.manager.block_cells(cells)
        self.manager.unblock_cells(cells)

        assert not self.manager.is_blocked(1, 1, 0)
        assert not self.manager.is_blocked(2, 2, 0)

    def test_mark_routed(self):
        """Test marking cells as routed."""
        cells = [(1, 1, 0), (2, 2, 0)]
        self.manager.mark_routed(cells, net_name="NetB")

        assert self.manager.is_occupied(1, 1, 0)
        assert self.manager.is_occupied(2, 2, 0)
        assert self.manager.get_cell_owner((1, 1, 0)) == "NetB"
        assert self.manager.get_cell_owner((2, 2, 0)) == "NetB"

    def test_rip_up_net(self):
        """Test ripping up a net."""
        cells1 = [(1, 1, 0), (2, 2, 0)]
        cells2 = [(3, 3, 0), (4, 4, 0)]

        self.manager.mark_routed(cells1, net_name="NetA")
        self.manager.mark_routed(cells2, net_name="NetB")

        freed = self.manager.rip_up_net("NetA")

        assert (1, 1, 0) in freed
        assert (2, 2, 0) in freed
        assert not self.manager.is_occupied(1, 1, 0)
        assert self.manager.is_occupied(3, 3, 0)  # NetB still there

    def test_get_cell_owner(self):
        """Test getting cell owner."""
        self.manager.mark_routed([(5, 5, 0)], net_name="NetC")

        assert self.manager.get_cell_owner((5, 5, 0)) == "NetC"
        assert self.manager.get_cell_owner((0, 0, 0)) is None

    def test_is_valid(self):
        """Test bounds checking."""
        assert self.manager._is_valid(9, 9, 1)  # Within bounds
        assert not self.manager._is_valid(10, 10, 2)  # Out of bounds
        assert not self.manager._is_valid(-1, 0, 0)  # Negative

    def test_clear_all(self):
        """Test clearing all occupancy."""
        self.manager.block_cells([(1, 1, 0)])
        self.manager.mark_routed([(2, 2, 0)], net_name="NetX")

        self.manager.clear_all()

        stats = self.manager.get_stats()
        assert stats["free_cells"] == 200
        assert stats["blocked_cells"] == 0
        assert stats["routed_cells"] == 0

    def test_resize(self):
        """Test resizing the grid."""
        self.manager.block_cells([(1, 1, 0)])
        self.manager.resize((5, 5))

        assert self.manager.grid_size == (5, 5)
        assert self.manager.occupancy.shape == (5, 5, 2)


class TestNetRouter:
    """Test cases for NetRouter."""

    def test_create_with_config(self):
        """Test creating NetRouter with custom config."""
        config = NetRouterConfig(max_iterations=5, via_cost=2.0)
        router = NetRouter(config=config)

        assert router.config.max_iterations == 5
        assert router.config.via_cost == 2.0

    def test_create_net_router_function(self):
        """Test the convenience function."""
        router = create_net_router(
            max_iterations=10,
            via_cost=5.0,
            strict_mode=True,
        )

        assert router.config.max_iterations == 10
        assert router.config.via_cost == 5.0
        assert router.config.strict_mode is True

    def test_route_without_maze_router(self):
        """Test routing fails gracefully without maze_router."""
        router = NetRouter()
        result = router.route("NetA", [])

        assert result.success is False
        assert "No maze_router configured" in result.failure_reason

    def test_net_router_result(self):
        """Test NetRouterResult dataclass."""
        result = NetRouterResult(
            success=True,
            net_name="TestNet",
            length=100.5,
            via_count=3,
        )

        assert result.success is True
        assert result.net_name == "TestNet"
        assert result.length == 100.5
        assert result.via_count == 3
        assert result.failure_reason is None

    def test_net_router_result_failure(self):
        """Test NetRouterResult with failure."""
        result = NetRouterResult(
            success=False,
            net_name="FailNet",
            failure_reason="No path found",
        )

        assert result.success is False
        assert result.failure_reason == "No path found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
