"""
Tests for parallel bus routing (temper-l4we.2).

Tests that the BusRouter can route all nets in a bus cohort in parallel,
maintaining consistent spacing and avoiding intra-bus crossings.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from temper_placer.core.bus_cohort import BusCohortConstraint
from temper_placer.routing.bus_router import BusRouter, BusRoutingResult


class TestBusRouterCreation:
    """Tests for BusRouter initialization."""

    def test_bus_router_requires_maze_router(self):
        """Should create BusRouter with maze_router reference."""
        mock_router = MagicMock()
        bus_router = BusRouter(mock_router)

        assert bus_router.maze_router is mock_router

    def test_bus_router_with_custom_config(self):
        """Should accept custom configuration."""
        mock_router = MagicMock()
        bus_router = BusRouter(
            mock_router,
            default_spacing_mm=0.3,
            max_offsets_try=5,
        )

        assert bus_router.default_spacing_mm == 0.3
        assert bus_router.max_offsets_try == 5


class TestRouteBusBasic:
    """Basic tests for routing a single bus."""

    def test_route_bus_returns_result(self):
        """route_bus should return BusRoutingResult."""
        mock_router = MagicMock()
        mock_router.route_net_rrr.return_value = MagicMock(
            success=True,
            cells=[],
            length=10.0,
            via_count=0,
        )

        bus_router = BusRouter(mock_router)
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["SPI_CLK", "SPI_MOSI", "SPI_MISO"],
        )

        result = bus_router.route_bus(bus, [(0, 0), (5, 0), (10, 0)], [(15, 0), (15, 5), (15, 10)])

        assert isinstance(result, BusRoutingResult)
        assert result.bus_name == "SPI_BUS"
        assert len(result.paths) == 3

    def test_route_bus_routes_reference_net_first(self):
        """First net in cohort should be routed as reference."""
        mock_router = MagicMock()
        mock_router.route_net_rrr.return_value = MagicMock(
            success=True,
            cells=[],
            length=10.0,
            via_count=0,
        )

        bus_router = BusRouter(mock_router)
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["SPI_CLK", "SPI_MOSI", "SPI_MISO"],
        )

        bus_router.route_bus(bus, [(0, 0), (5, 0), (10, 0)], [(15, 0), (15, 5), (15, 10)])

        mock_router.route_net_rrr.assert_called_once()
        call_args = mock_router.route_net_rrr.call_args
        assert call_args[1]["net_name"] == "SPI_CLK"

    def test_route_bus_generates_parallel_paths(self):
        """Should generate parallel paths for non-reference nets."""
        mock_router = MagicMock()
        mock_router.cell_size = 0.2
        mock_router.grid_size = (50, 50)
        mock_router._world_to_grid.return_value = (5, 0)
        mock_router.occupancy = np.zeros((50, 50, 1), dtype=np.int32)

        ref_path = MagicMock()
        ref_path.cells = [
            MagicMock(x=0, y=0, layer=0),
            MagicMock(x=1, y=0, layer=0),
            MagicMock(x=2, y=0, layer=0),
            MagicMock(x=3, y=0, layer=0),
        ]
        ref_path.success = True
        ref_path.length = 3.0
        ref_path.via_count = 0
        ref_path.cell_size = 0.2
        ref_path.trace_width = 0.2
        ref_path.via_diameter = 0.6
        ref_path.via_drill = 0.3

        mock_router.route_net_rrr.return_value = ref_path

        bus_router = BusRouter(mock_router)
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["SPI_CLK", "SPI_MOSI"],
            pitch_mm=0.4,
        )

        result = bus_router.route_bus(bus, [(0, 0), (5, 0)], [(15, 0), (15, 5)])

        assert len(result.paths) == 2
        assert "SPI_CLK" in result.paths
        assert "SPI_MOSI" in result.paths

    def test_route_bus_all_paths_successful(self):
        """All paths in bus should be marked successful."""
        mock_router = MagicMock()
        mock_router.route_net_rrr.return_value = MagicMock(
            success=True,
            cells=[],
            length=10.0,
            via_count=0,
        )

        bus_router = BusRouter(mock_router)
        bus = BusCohortConstraint(
            name="I2C_BUS",
            nets=["I2C_SDA", "I2C_SCL"],
        )

        result = bus_router.route_bus(bus, [(0, 0), (5, 0)], [(10, 0), (10, 5)])

        for net, path in result.paths.items():
            assert path.success is True, f"Net {net} should be successful"


class TestParallelPathGeneration:
    """Tests for generating parallel paths from reference."""

    def test_offset_path_perpendicular(self):
        """Should offset path perpendicularly."""
        mock_router = MagicMock()

        ref_path = MagicMock()
        ref_path.cells = [
            MagicMock(x=0, y=0, layer=0),
            MagicMock(x=1, y=0, layer=0),
            MagicMock(x=2, y=0, layer=0),
        ]

        bus_router = BusRouter(mock_router)
        offset_path = bus_router._offset_path(ref_path, offset_mm=0.4)

        assert len(offset_path.cells) == len(ref_path.cells)

    def test_offset_preserves_via_count(self):
        """Offset path should have same via count as reference."""
        mock_router = MagicMock()

        ref_path = MagicMock()
        ref_path.cells = [
            MagicMock(x=0, y=0, layer=0),
            MagicMock(x=1, y=0, layer=0),
            MagicMock(x=1, y=1, layer=0),
            MagicMock(x=1, y=1, layer=1),
            MagicMock(x=2, y=1, layer=1),
        ]

        bus_router = BusRouter(mock_router)
        offset_path = bus_router._offset_path(ref_path, offset_mm=0.4)

        assert offset_path.via_count == ref_path.via_count

    def test_negative_offset_opposite_direction(self):
        """Negative offset should go opposite direction."""
        mock_router = MagicMock()
        mock_router.cell_size = 0.2
        mock_router.grid_size = (50, 50)

        ref_path = MagicMock()
        ref_path.cells = [
            MagicMock(x=0, y=0, layer=0),
            MagicMock(x=1, y=0, layer=0),
            MagicMock(x=2, y=0, layer=0),
        ]
        ref_path.success = True
        ref_path.length = 2.0
        ref_path.via_count = 0
        ref_path.cell_size = 0.2
        ref_path.trace_width = 0.2
        ref_path.via_diameter = 0.6
        ref_path.via_drill = 0.3

        bus_router = BusRouter(mock_router)
        pos_offset = bus_router._offset_path(ref_path, offset_mm=0.4)
        neg_offset = bus_router._offset_path(ref_path, offset_mm=-0.4)

        assert pos_offset.cells[1].y != neg_offset.cells[1].y


class TestObstacleAvoidance:
    """Tests for handling obstacles during parallel routing."""

    def test_obstacle_causes_reroute_with_wider_channel(self):
        """Should re-route reference when parallel path hits obstacle.

        Note: This test requires a real maze_router with proper occupancy tracking.
        Skipping in unit test mode.
        """
        pytest.skip("Requires real maze_router integration")

    def test_multiple_obstacles_try_multiple_offsets(self):
        """Should try multiple offset directions when obstacles found.

        Note: This test requires a real maze_router with proper occupancy tracking.
        Skipping in unit test mode.
        """
        pytest.skip("Requires real maze_router integration")


class TestBusRoutingResult:
    """Tests for BusRoutingResult structure."""

    def test_result_contains_all_paths(self):
        """Result should have path for each net in bus."""
        mock_router = MagicMock()
        mock_router.route_net_rrr.return_value = MagicMock(
            success=True,
            cells=[],
            length=10.0,
            via_count=0,
        )

        bus_router = BusRouter(mock_router)
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["CLK", "MOSI", "MISO", "CS"],
        )

        result = bus_router.route_bus(
            bus, [(0, 0), (5, 0), (10, 0), (15, 0)], [(20, 0), (20, 5), (20, 10), (20, 15)]
        )

        assert len(result.paths) == 4
        assert set(result.paths.keys()) == {"CLK", "MOSI", "MISO", "CS"}

    def test_result_tracks_spacing(self):
        """Result should track achieved spacing."""
        mock_router = MagicMock()
        mock_router.route_net_rrr.return_value = MagicMock(
            success=True,
            cells=[],
            length=10.0,
            via_count=0,
        )

        bus_router = BusRouter(mock_router)
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["A", "B"],
            pitch_mm=0.4,
        )

        result = bus_router.route_bus(bus, [(0, 0), (5, 0)], [(10, 0), (10, 5)])

        assert result.achieved_spacing_mm is not None
        assert result.achieved_spacing_mm > 0

    def test_result_no_intra_bus_crossings(self):
        """Result should report if intra-bus crossings detected."""
        mock_router = MagicMock()
        mock_router.route_net_rrr.return_value = MagicMock(
            success=True,
            cells=[],
            length=10.0,
            via_count=0,
        )

        bus_router = BusRouter(mock_router)
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["A", "B"],
        )

        result = bus_router.route_bus(bus, [(0, 0), (5, 0)], [(10, 0), (10, 5)])

        assert result.intra_bus_crossings == 0


class TestBusRoutingIntegration:
    """Integration tests for bus routing."""

    def test_spi_bus_routing(self):
        """Should route complete SPI bus successfully."""
        mock_router = MagicMock()
        mock_router.route_net_rrr.return_value = MagicMock(
            success=True,
            cells=[],
            length=10.0,
            via_count=0,
        )

        bus_router = BusRouter(mock_router)
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS"],
            pitch_mm=0.4,
            max_skew_mm=2.0,
        )

        result = bus_router.route_bus(
            bus,
            [(2.5, 5.0), (2.5, 6.0), (2.5, 7.0), (2.5, 8.0)],
            [(47.5, 5.0), (47.5, 6.0), (47.5, 7.0), (47.5, 8.0)],
        )

        assert result.success
        assert len(result.paths) == 4
        assert result.bus_name == "SPI_BUS"

    def test_differential_pair_routing(self):
        """Should route differential pair with tight spacing."""
        mock_router = MagicMock()
        mock_router.route_net_rrr.return_value = MagicMock(
            success=True,
            cells=[],
            length=10.0,
            via_count=0,
        )

        bus_router = BusRouter(mock_router, default_spacing_mm=0.2)
        bus = BusCohortConstraint(
            name="DIFF_USB",
            nets=["USB_DP", "USB_DN"],
            pitch_mm=0.3,
        )

        result = bus_router.route_bus(bus, [(0, 0), (5, 0)], [(50, 0), (50, 5)])

        assert result.success
        assert len(result.paths) == 2
