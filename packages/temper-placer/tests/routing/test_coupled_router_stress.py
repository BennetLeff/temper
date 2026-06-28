"""
Dense-area stress test for CoupledDiffPairRouter coarse A* waypoint planner.

The coarse A* planner uses ~1mm grid resolution, 10x coarser than the
fine grid (0.1mm). In congested regions, coarse waypoints can steer into
dead ends the fine-segment router can't resolve. This test verifies the
router avoids that failure mode.
"""

import pytest
from typing import Set, Tuple

from temper_placer.routing.coupled_diff_pair_router import CoupledDiffPairRouter


class TestDenseAreaStress:
    """Stress tests for the hierarchical waypoint planner in dense regions."""

    def test_single_pad_between_pins(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )
        result = coupled.route_hierarchical(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((10, 0), (10, 0.25)),
            obstacles=_block(5, 0, 1, 2),
            board_size=(15, 5, 2),
            obstacle_grid_resolution_mm=0.1,
        )
        assert result.success, (
            f"Should find path around single pad obstacle: {result.error_message}"
        )

    def test_dense_cluster_of_pads(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )
        obstacles = set()
        for px in (4, 5, 6):
            for py in (-1, 0, 1):
                obstacles |= _block(px, py, 0.5, 0.5)

        result = coupled.route_hierarchical(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((10, 0), (10, 0.25)),
            obstacles=obstacles,
            board_size=(15, 5, 2),
            obstacle_grid_resolution_mm=0.1,
        )
        assert result.success, (
            f"Should navigate dense pad cluster: {result.error_message}"
        )
        assert result.coupling_ratio >= 50.0

    def test_wall_of_pads_above_and_below(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )
        obstacles = set()
        for px in range(35, 65):
            obstacles |= _block(px / 10.0, -0.5, 0.3, 0.3)
            obstacles |= _block(px / 10.0, 1.0, 0.3, 0.3)

        result = coupled.route_hierarchical(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((10, 0), (10, 0.25)),
            obstacles=obstacles,
            board_size=(15, 5, 2),
            obstacle_grid_resolution_mm=0.1,
        )
        assert result.success, (
            f"Should find gap through wall of pads: {result.error_message}"
        )
        assert result.coupling_ratio >= 50.0

    def test_coarse_waypoints_not_steered_into_dead_end(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )
        obstacles = set()
        for x in range(30, 70):
            obstacles |= _block(x / 10.0, -2.0, 1.2, 1.2)
            obstacles |= _block(x / 10.0, 2.5, 1.2, 1.2)

        result = coupled.route_hierarchical(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((10, 0), (10, 0.25)),
            obstacles=obstacles,
            board_size=(15, 5, 2),
            obstacle_grid_resolution_mm=0.1,
        )
        assert result.success, (
            f"Should find narrow corridor: {result.error_message}"
        )


def _block(
    cx: float, cy: float,
    radius_mm: float = 1.0, height_mm: float = 2.0,
    resolution: float = 0.1, layer: int = 0,
) -> Set[Tuple[int, int, int]]:
    obs = set()
    hw = int(radius_mm / resolution) + 1
    hh = int(height_mm / resolution) + 1
    ix = int(cx / resolution)
    iy = int(cy / resolution)
    for dx in range(-hw, hw + 1):
        for dy in range(-hh, hh + 1):
            obs.add((ix + dx, iy + dy, layer))
    return obs
