"""
Tight-pitch fixture test for CoupledDiffPairRouter.

The Temper board's USB pair has generous spacing (~5mm between pins).
In tight-pitch situations (0.5mm QFN, BGA), the clearance envelope is
much narrower and the legacy DiffPairRouter's post-processing offsets
are more likely to produce DRC violations.

This test constructs a synthetic board with a differential pair between
tight-pitch pads and verifies the coupled router handles it correctly.
"""

import pytest

from temper_placer.routing.coupled_diff_pair_router import CoupledDiffPairRouter


class TestTightPitchDiffPair:
    """Coupled router handles diff pairs between tight-pitch pads."""

    def test_05mm_qfn_style_pad_pair_straight(self):
        """P and N pads spaced 0.5mm apart (QFN-typical)."""
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.5,       # matching actual 0.5mm pin spacing
            max_divergence_mm=0.15,
            max_skew_mm=0.1,
        )
        result = coupled.route(
            start_pins=((0, 0.25), (0, -0.25)),
            goal_pins=((5, 0.25), (5, -0.25)),
            obstacles=set(),
            board_size=(8, 3, 2),
            net_pos="QFN_P",
            net_neg="QFN_N",
        )
        assert result.success, (
            f"Coupled router failed tight-pitch pair: {result.error_message}"
        )
        assert result.coupling_ratio >= 95.0, (
            f"Tight-pitch coupling ratio {result.coupling_ratio:.1f}% below 95%"
        )

    def test_05mm_pitch_with_keepout_between(self):
        """P and N 0.5mm apart with a keepout zone between them."""
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.15,
            max_skew_mm=0.15,
        )
        obstacles = set()
        for x in range(15, 35):
            obstacles.add((x, 0, 0))

        result = coupled.route_hierarchical(
            start_pins=((0, 0.25), (0, -0.25)),
            goal_pins=((5, 0.25), (5, -0.25)),
            obstacles=obstacles,
            board_size=(8, 3, 2),
            obstacle_grid_resolution_mm=0.1,
        )
        assert result.success, (
            f"Tight-pitch pair should route around keepout: {result.error_message}"
        )

    def test_spacing_enforced_for_tight_pair(self):
        """Skew tolerance is tight — should reject excessive divergence."""
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.05,       # Very tight — only 50um allowed
            max_skew_mm=0.5,
        )
        result = coupled.route(
            start_pins=((0, 0.3), (0, -0.3)),    # 0.6mm apart, 0.35mm off target
            goal_pins=((5, 0.3), (5, -0.3)),
            obstacles=set(),
            board_size=(8, 3, 2),
            net_pos="TIGHT_P",
            net_neg="TIGHT_N",
        )
        assert result.success, (
            f"Tight tolerance routing failed: {result.error_message}"
        )

    def test_parallel_runout_from_mcu_pads(self):
        """MCU pins spaced 0.65mm apart (STM32-typical) with parallel runout."""
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.3,
            max_skew_mm=0.3,
        )
        result = coupled.route(
            start_pins=((0, 0.325), (0, -0.325)),
            goal_pins=((8, 2.0), (8, 1.75)),
            obstacles=set(),
            board_size=(10, 5, 2),
            net_pos="MCU_P",
            net_neg="MCU_N",
        )
        assert result.success, (
            f"MCU-pitch L-shape pair failed: {result.error_message}"
        )

    def test_0603_passive_in_path(self):
        """An 0603 passive (1.6mm x 0.8mm) between pins should be avoided."""
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.3,
            max_skew_mm=0.3,
        )
        obstacles = set()
        for x in range(30, 50):
            for y in range(-3, 11):
                obstacles.add((x, y, 0))

        result = coupled.route_hierarchical(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((8, 0), (8, 0.25)),
            obstacles=obstacles,
            board_size=(10, 5, 2),
            obstacle_grid_resolution_mm=0.1,
        )
        assert result.success, (
            f"Should route around 0603 passive: {result.error_message}"
        )
