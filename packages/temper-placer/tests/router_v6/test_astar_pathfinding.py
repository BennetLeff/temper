"""
Tests for Router V6 Stage 4.2: Run A* Pathfinding

Part of temper-x2xd
"""

import numpy as np
import pytest

from temper_placer.router_v6.astar_pathfinding import (
    PathfindingResult,
    RoutePath,
    run_astar_pathfinding,
)
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


@pytest.mark.l4_regression
def test_run_empty_pathfinding():
    """Test pathfinding with no nets."""
    mapping = ChannelMapping(channel_paths={})
    grid = OccupancyGrid("F.Cu", np.zeros((10, 10), dtype=np.int8), (0, 0), 1.0, 10, 10)

    result = run_astar_pathfinding(mapping, grid)

    assert result.success_count == 0
    assert result.failure_count == 0


@pytest.mark.l4_regression
def test_run_simple_pathfinding():
    """Test pathfinding with simple channel path."""
    channel_path = ChannelPath(
        net_name="NET1",
        channel_sequence=["CH1", "CH2"],
        waypoints=[(0.0, 0.0), (10.0, 10.0)],
        total_length=14.14,
    )

    mapping = ChannelMapping(channel_paths={"NET1": channel_path})
    grid = OccupancyGrid("F.Cu", np.zeros((20, 20), dtype=np.int8), (0, 0), 1.0, 20, 20)

    result = run_astar_pathfinding(mapping, grid)

    assert result.success_count == 1
    assert result.failure_count == 0

    path = result.get_path("NET1")
    assert path is not None
    assert path.net_name == "NET1"
    assert len(path.coordinates) > 0


@pytest.mark.l4_regression
def test_route_path_dataclass():
    """Test RoutePath dataclass."""
    path = RoutePath(
        net_name="TEST_NET",
        coordinates=[(0, 0), (5, 5), (10, 10)],
        layer_name="F.Cu",
        path_length=14.14,
    )

    assert path.net_name == "TEST_NET"
    assert path.segment_count == 2
    assert len(path.coordinates) == 3
    assert path.layer_name == "F.Cu"


@pytest.mark.l4_regression
def test_pathfinding_result_dataclass():
    """Test PathfindingResult dataclass."""
    path1 = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    path2 = RoutePath("NET2", [(5, 5), (15, 15)], "F.Cu", 14.14)

    result = PathfindingResult(
        routed_paths={"NET1": path1, "NET2": path2},
        failed_nets=["NET3"],
    )

    assert result.success_count == 2
    assert result.failure_count == 1
    assert result.get_path("NET1") == path1
    assert result.get_path("NET2") == path2
    assert result.get_path("NET3") is None


@pytest.mark.l4_regression
def test_pathfinding_with_multiple_nets():
    """Test pathfinding with multiple nets."""
    path1 = ChannelPath("NET1", ["CH1"], [(0, 0), (5, 5)], 7.07)
    path2 = ChannelPath("NET2", ["CH2"], [(10, 10), (15, 15)], 7.07)

    mapping = ChannelMapping(channel_paths={"NET1": path1, "NET2": path2})
    grid = OccupancyGrid("F.Cu", np.zeros((20, 20), dtype=np.int8), (0, 0), 1.0, 20, 20)

    result = run_astar_pathfinding(mapping, grid)

    assert result.success_count == 2
    assert result.failure_count == 0
