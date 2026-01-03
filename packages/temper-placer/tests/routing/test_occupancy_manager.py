"""Tests for OccupancyManager."""

import numpy as np
import pytest

from temper_placer.routing.occupancy import OccupancyManager


class TestOccupancyManagerBasics:
    """Test basic initialization and cell status."""

    def test_initial_state(self):
        manager = OccupancyManager((10, 10), num_layers=2)
        assert manager.grid_size == (10, 10)
        assert manager.num_layers == 2
        assert manager.occupancy.shape == (10, 10, 2)
        assert np.all(manager.occupancy == manager.FREE)
        assert np.all(manager.congestion == 0.0)

    def test_block_cell(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.block_cell(5, 5, 0)
        assert manager.occupancy[5, 5, 0] == manager.BLOCKED

    def test_block_cells(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        cells = [(1, 2, 0), (3, 4, 0), (5, 6, 0)]
        manager.block_cells(cells)
        for x, y, layer in cells:
            assert manager.occupancy[x, y, layer] == manager.BLOCKED

    def test_unblock_cell(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.block_cell(5, 5, 0)
        manager.unblock_cell(5, 5, 0)
        assert manager.occupancy[5, 5, 0] == manager.FREE

    def test_is_blocked(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        assert manager.is_blocked(5, 5, 0) == False
        manager.block_cell(5, 5, 0)
        assert manager.is_blocked(5, 5, 0) == True

    def test_is_occupied(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        assert manager.is_occupied(5, 5, 0) == False
        manager.mark_routed([(5, 5, 0)], "net_a")
        assert manager.is_occupied(5, 5, 0) == True

    def test_is_free(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        assert manager.is_free(5, 5, 0) == True
        manager.block_cell(5, 5, 0)
        assert manager.is_free(5, 5, 0) == False
        manager.mark_routed([(5, 5, 0)], "net_a")
        assert manager.is_free(5, 5, 0) == False

    def test_out_of_bounds(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        assert manager.is_blocked(-1, 5, 0) == True
        assert manager.is_blocked(10, 5, 0) == True
        assert manager.is_blocked(5, -1, 0) == True
        assert manager.is_blocked(5, 10, 0) == True
        assert manager.is_blocked(5, 5, 1) == True
        assert manager.is_blocked(5, 5, -1) == True


class TestNetOwnership:
    """Test net ID assignment and cell ownership."""

    def test_get_net_id(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        net_id1 = manager.get_net_id("net_a")
        net_id2 = manager.get_net_id("net_b")
        net_id1_again = manager.get_net_id("net_a")
        assert net_id1 == net_id1_again
        assert net_id1 != net_id2
        assert net_id1 == 1
        assert net_id2 == 2

    def test_mark_routed_sets_owner(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        net_id = manager.get_net_id("net_a")
        manager.mark_routed([(5, 5, 0)], "net_a")
        assert manager.get_cell_owner(5, 5, 0) == "net_a"
        assert manager.owner_grid[5, 5, 0] == net_id

    def test_mark_routed_multiple_cells(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.mark_routed([(1, 1, 0), (2, 2, 0), (3, 3, 0)], "net_a")
        assert manager.get_cell_owner(1, 1, 0) == "net_a"
        assert manager.get_cell_owner(2, 2, 0) == "net_a"
        assert manager.get_cell_owner(3, 3, 0) == "net_a"

    def test_multiple_nets_same_cell(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.mark_routed([(5, 5, 0)], "net_a")
        manager.mark_routed([(5, 5, 0)], "net_b")
        assert manager.get_cell_owner(5, 5, 0) == "net_a"
        assert manager.owner_grid[5, 5, 0] == 1

    def test_rip_up_net_removes_ownership(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.mark_routed([(5, 5, 0)], "net_a")
        manager.rip_up_net("net_a", [(5, 5, 0)])
        assert manager.get_cell_owner(5, 5, 0) is None

    def test_rip_up_net_preserves_if_other_net(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.mark_routed([(5, 5, 0)], "net_a")
        manager.mark_routed([(5, 5, 0)], "net_b")
        manager.rip_up_net("net_a", [(5, 5, 0)])
        assert manager.get_cell_owner(5, 5, 0) == "net_b"


class TestCongestionTracking:
    """Test congestion tracking functionality."""

    def test_congestion_increases(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.mark_routed([(5, 5, 0)], "net_a")
        manager.mark_routed([(5, 5, 0)], "net_b")
        assert manager.congestion[5, 5, 0] == 2.0

    def test_congestion_decreases_on_rip_up(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.mark_routed([(5, 5, 0)], "net_a")
        manager.mark_routed([(5, 5, 0)], "net_b")
        manager.rip_up_net("net_a", [(5, 5, 0)])
        assert manager.congestion[5, 5, 0] == 1.0

    def test_congestion_not_negative(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.rip_up_net("net_a", [(5, 5, 0)])
        assert manager.congestion[5, 5, 0] == 0.0

    def test_get_stats(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.block_cell(0, 0, 0)
        manager.mark_routed([(1, 1, 0)], "net_a")
        manager.mark_routed([(1, 1, 0)], "net_b")
        stats = manager.get_stats()
        assert stats["blocked_cells"] == 1
        assert stats["routed_cells"] == 1
        assert stats["congested_cells"] == 1
        assert stats["free_cells"] == 98


class TestMultiLayer:
    """Test multi-layer functionality."""

    def test_multi_layer_blocking(self):
        manager = OccupancyManager((10, 10), num_layers=3)
        manager.block_cell(5, 5, 0)
        manager.block_cell(5, 5, 1)
        manager.block_cell(5, 5, 2)
        assert manager.occupancy[5, 5, 0] == manager.BLOCKED
        assert manager.occupancy[5, 5, 1] == manager.BLOCKED
        assert manager.occupancy[5, 5, 2] == manager.BLOCKED

    def test_layer_isolation(self):
        manager = OccupancyManager((10, 10), num_layers=2)
        manager.mark_routed([(5, 5, 0)], "net_a")
        assert manager.is_occupied(5, 5, 0) == True
        assert manager.is_occupied(5, 5, 1) == False


class TestClearAndResize:
    """Test clear and resize functionality."""

    def test_clear_all(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.block_cell(0, 0, 0)
        manager.mark_routed([(1, 1, 0)], "net_a")
        manager.clear_all()
        assert manager.get_stats()["blocked_cells"] == 0
        assert manager.get_stats()["routed_cells"] == 0
        assert np.all(manager.occupancy == manager.FREE)

    def test_resize(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.block_cell(0, 0, 0)
        manager.mark_routed([(1, 1, 0)], "net_a")
        manager.resize((20, 20))
        assert manager.grid_size == (20, 20)
        assert manager.occupancy.shape == (20, 20, 1)


class TestGetAllRoutedCells:
    """Test getting all routed cells."""

    def test_get_all_routed_cells_all(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.mark_routed([(1, 1, 0), (2, 2, 0)], "net_a")
        manager.mark_routed([(3, 3, 0)], "net_b")
        cells = manager.get_all_routed_cells()
        assert len(cells) == 3
        assert (1, 1, 0) in cells
        assert (2, 2, 0) in cells
        assert (3, 3, 0) in cells

    def test_get_all_routed_cells_filtered(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.mark_routed([(1, 1, 0), (2, 2, 0)], "net_a")
        manager.mark_routed([(3, 3, 0)], "net_b")
        cells = manager.get_all_routed_cells("net_a")
        assert len(cells) == 2
        assert (1, 1, 0) in cells
        assert (2, 2, 0) in cells
        assert (3, 3, 0) not in cells


class TestGetOccupancy:
    """Test get_occupancy method."""

    def test_get_occupancy_free(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        assert manager.get_occupancy(5, 5, 0) == manager.FREE

    def test_get_occupancy_blocked(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        manager.block_cell(5, 5, 0)
        assert manager.get_occupancy(5, 5, 0) == manager.BLOCKED

    def test_get_occupancy_out_of_bounds(self):
        manager = OccupancyManager((10, 10), num_layers=1)
        assert manager.get_occupancy(-1, 5, 0) == manager.BLOCKED
