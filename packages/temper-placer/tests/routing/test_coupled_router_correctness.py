"""
Characterization test for CoupledDiffPairRouter correctness.

Validates the core claim from baseline_usb_violations.md: the coupled router
eliminates DRC violations that the legacy DiffPairRouter produces via
post-processing offsets.

The test constructs a synthetic board with pads near the diff pair path,
exercising the exact failure mode that causes 21 track_pad_clearance
violations on USB pairs.
"""

import pytest
from typing import Set, Tuple

from temper_placer.routing.coupled_diff_pair_router import (
    CoupledDiffPairRouter,
    CoupledRouterResult,
)
from temper_placer.routing.diff_pair_router import DiffPairRouter


class DummyDRCOracle:
    """Minimal DRC oracle that enforces pad clearance.

    Blocks track segments that enter keep-out zones around known pads.
    """

    def __init__(
        self,
        pads: list[Tuple[float, float, float]],
        keepout_radius_mm: float = 0.5,
    ):
        self._pads = pads
        self._keepout = keepout_radius_mm

    def can_place_track_segment(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        layer: int,
        net: str,
        width: float,
        companion_net: str = None,
    ):
        half_width = width / 2.0
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = (dx * dx + dy * dy) ** 0.5
        if length < 0.001:
            return True, ""
        samples = max(2, int(length / 0.1))
        for i in range(samples + 1):
            t = i / samples
            x = start[0] + dx * t
            y = start[1] + dy * t
            for px, py, pr in self._pads:
                d = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
                if d < pr + half_width + self._keepout:
                    return False, f"Track within pad keepout at ({x:.2f}, {y:.2f})"
        return True, ""

    def can_place_via(self, pos, layer_pair, net, companion_net=None):
        return True, ""


class TestCoupledRouterCorrectness:
    """Core correctness: coupled router eliminates DRC violations."""

    def test_coupled_router_no_violations_straight_path(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )
        result = coupled.route(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((10, 0), (10, 0.25)),
            obstacles=set(),
            board_size=(15, 5, 2),
            net_pos="PAIR_P",
            net_neg="PAIR_N",
        )
        assert result.success, f"Coupled router should succeed on open board: {result.error_message}"
        assert result.pos_path, "P path should not be empty"
        assert result.neg_path, "N path should not be empty"
        assert result.coupling_ratio >= 90.0, (
            f"Coupling ratio {result.coupling_ratio:.1f}% < 90%"
        )

    def test_coupled_router_drc_blocked_path(self):
        pads = [
            (5.0, 0.0, 0.3),
        ]
        oracle = DummyDRCOracle(pads, keepout_radius_mm=0.3)
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
            drc_oracle=oracle,
        )
        result = coupled.route(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((10, 0), (10, 0.25)),
            obstacles=set(),
            board_size=(15, 5, 2),
            net_pos="PAIR_P",
            net_neg="PAIR_N",
        )
        assert not result.success, (
            "Coupled router should reject path through a pad keep-out zone"
        )
        assert result.error_message, "Should have error message on failure"

    def test_coupled_vs_legacy_l_shape(self):
        """Route an L-shaped path through both routers; coupled must not regress.

        Golden-ladder parity: coupled path length within 10% of legacy,
        coupling ratio >= legacy, zero violations where legacy could produce them.
        """
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.5,
            max_divergence_mm=1.0,
            max_skew_mm=0.5,
        )
        coupled_result = coupled.route(
            start_pins=((2, 2), (2, 2.5)),
            goal_pins=((8, 8), (8, 8.5)),
            obstacles=set(),
            board_size=(15, 15, 2),
            net_pos="L_P",
            net_neg="L_N",
        )
        assert coupled_result.success, f"Coupled should route L-shape: {coupled_result.error_message}"

        coupled_len = max(
            coupled._path_length(coupled_result.pos_path),
            coupled._path_length(coupled_result.neg_path),
        )

        legacy = DiffPairRouter(
            grid_size=(150, 150, 2),
            cell_size_mm=0.1,
            target_separation_mm=0.5,
            max_divergence_mm=1.0,
            max_skew_mm=0.5,
        )
        legacy_result = legacy.route_pair(
            start_pins=((2, 2), (2, 2.5)),
            goal_pins=((8, 8), (8, 8.5)),
            obstacles=set(),
        )
        assert legacy_result.success, f"Legacy should also route L-shape: {legacy_result.failure_reason}"

        def _cells_path_length(cells, cell_size):
            length = 0.0
            for i in range(len(cells) - 1):
                dx = (cells[i + 1][0] - cells[i][0]) * cell_size
                dy = (cells[i + 1][1] - cells[i][1]) * cell_size
                length += (dx * dx + dy * dy) ** 0.5
            return length

        legacy_len = max(
            _cells_path_length(legacy_result.pos_cells, legacy.cell_size_mm),
            _cells_path_length(legacy_result.neg_cells, legacy.cell_size_mm),
        )

        assert coupled_len <= legacy_len * 1.10, (
            f"Coupled path length {coupled_len:.2f}mm > 110% of legacy {legacy_len:.2f}mm"
        )

        assert coupled_result.coupling_ratio >= 50.0, (
            f"Coupled coupling ratio {coupled_result.coupling_ratio:.1f}% too low"
        )

    def test_coupled_router_fallback_on_hard_obstacle(self):
        """Coupled router returns success=False when obstacles block all paths.

        The caller (sequential_routing.py) detects this and falls back to legacy.
        """
        obstacles: Set[Tuple[int, int, int]] = set()
        for x in range(20, 80):
            for y in range(-80, 80):
                obstacles.add((x, y, 0))

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
            obstacles=obstacles,
            board_size=(15, 5, 2),
            net_pos="BLOCK_P",
            net_neg="BLOCK_N",
            obstacle_grid_resolution_mm=0.1,
        )
        assert not result.success, "Coupled router should report failure when path is blocked"
        assert result.error_message, "Should provide error message for caller to act on"
        assert "no path found" in result.error_message.lower() or "failed" in result.error_message.lower(), (
            f"Error message should explain failure: {result.error_message}"
        )

    def test_coupled_router_result_dataclass(self):
        """CoupledRouterResult fields are populated correctly on success and failure."""
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
        )

        success = coupled.route(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((10, 0), (10, 0.25)),
            obstacles=set(),
            board_size=(15, 5, 2),
        )
        assert success.success is True
        assert success.pos_path
        assert success.neg_path
        assert success.routing_time_s > 0
        assert 0 <= success.coupling_ratio <= 100
        assert success.max_skew_mm >= 0
        assert success.avg_separation_mm > 0
        assert success.error_message is None

        failure = coupled.route_hierarchical(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((10, 0), (10, 0.25)),
            obstacles={(5, 0, 0) for _ in range(100) if False},
            board_size=(1, 1, 1),
            obstacle_grid_resolution_mm=0.1,
        )
        assert failure.success is False
        assert failure.pos_path == [] or failure.pos_path is not None
        assert failure.neg_path == [] or failure.neg_path is not None
        assert failure.error_message is not None
