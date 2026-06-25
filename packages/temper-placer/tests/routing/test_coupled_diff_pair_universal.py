"""
Integration tests for the universalized CoupledDiffPairRouter.

Verifies that non-USB diff pairs are correctly inferred and routed through
the DRC-oracle-validated coupled router path.
"""

import pytest

from temper_placer.router_v6.diff_pair_inference import DiffPair, infer_differential_pairs
from temper_placer.routing.coupled_diff_pair_router import (
    CoupledDiffPairRouter,
    CoupledRouterResult,
)


class TestNonUSBDiffPairInference:
    """Diff pair inference covers non-USB pairs."""

    def test_infers_i_sense_pair(self):
        pairs = infer_differential_pairs(["I_SENSE_P", "I_SENSE_N", "GND"])
        assert len(pairs) == 1
        assert pairs[0].base_name == "I_SENSE"
        assert pairs[0].p_net == "I_SENSE_P"
        assert pairs[0].n_net == "I_SENSE_N"

    def test_infers_spi_clock_pair_plus_minus(self):
        pairs = infer_differential_pairs(["SPI_CLK+", "SPI_CLK-", "VCC"])
        assert len(pairs) == 1
        pair = pairs[0]
        assert pair.base_name == "SPI_CLK"
        assert pair.p_net.endswith("+")
        assert pair.n_net.endswith("-")

    def test_infers_clock_pair_p_n(self):
        pairs = infer_differential_pairs(["CLK_P", "CLK_N", "RST"])
        assert len(pairs) == 1
        assert pairs[0].base_name == "CLK"

    def test_infers_dp_dn_suffix(self):
        pairs = infer_differential_pairs(["ETH_DP", "ETH_DN"])
        assert len(pairs) == 1
        assert pairs[0].base_name == "ETH"

    def test_handles_no_diff_pairs(self):
        pairs = infer_differential_pairs(["GND", "VCC", "RST"])
        assert len(pairs) == 0

    def test_handles_empty_list(self):
        pairs = infer_differential_pairs([])
        assert len(pairs) == 0

    def test_diff_pair_validation_rejects_identical_nets(self):
        with pytest.raises(ValueError, match="must be different"):
            DiffPair(base_name="BAD", p_net="SAME", n_net="SAME")


class TestNonUSBCoupledRouting:
    """Non-USB diff pairs route successfully through the coupled router."""

    def test_i_sense_straight_path(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.15,
            target_spacing_mm=0.2,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )
        result = coupled.route(
            start_pins=((0, 5), (0, 5.2)),
            goal_pins=((10, 5), (10, 5.2)),
            obstacles=set(),
            board_size=(15, 10, 2),
            net_pos="I_SENSE_P",
            net_neg="I_SENSE_N",
        )
        assert result.success, f"Coupled router failed I_SENSE pair: {result.error_message}"
        assert len(result.pos_path) > 0
        assert len(result.neg_path) > 0
        assert result.coupling_ratio >= 90.0

    def test_spi_clock_l_shape_path(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=1.0,
            max_skew_mm=0.5,
        )
        result = coupled.route(
            start_pins=((1, 1), (1, 1.25)),
            goal_pins=((7, 5), (7, 5.25)),
            obstacles=set(),
            board_size=(10, 8, 2),
            net_pos="SPI_CLK+",
            net_neg="SPI_CLK-",
        )
        assert result.success, f"Coupled router failed SPI pair: {result.error_message}"
        assert result.coupling_ratio > 0

    def test_failure_reports_meaningful_error(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )
        result = coupled.route_hierarchical(
            start_pins=((0, 0), (0, 0.25)),
            goal_pins=((5, 0), (5, 0.25)),
            obstacles=set(),
            board_size=(0.5, 0.5, 1),
            net_pos="CLK_P",
            net_neg="CLK_N",
            obstacle_grid_resolution_mm=0.1,
        )
        assert not result.success
        assert result.error_message is not None

    def test_eth_dp_dn_straight_path(self):
        coupled = CoupledDiffPairRouter(
            grid_resolution_mm=0.1,
            trace_width_mm=0.127,
            target_spacing_mm=0.25,
            max_divergence_mm=0.5,
            max_skew_mm=0.5,
        )
        result = coupled.route(
            start_pins=((0, 3), (0, 3.25)),
            goal_pins=((12, 3), (12, 3.25)),
            obstacles=set(),
            board_size=(15, 6, 2),
            net_pos="ETH_DP",
            net_neg="ETH_DN",
        )
        assert result.success, f"Coupled router failed ETH pair: {result.error_message}"
        assert len(result.pos_path) > 0


class TestPackageImport:
    """The promoted router imports cleanly from the routing package."""

    def test_direct_import(self):
        from temper_placer.routing import CoupledDiffPairRouter, CoupledRouterResult

        router = CoupledDiffPairRouter()
        assert router is not None

    def test_import_from_coupled_diff_pair_router(self):
        from temper_placer.routing.coupled_diff_pair_router import (
            CoupledDiffPairRouter,
            CoupledRouterResult,
        )

        result = CoupledRouterResult(
            success=True,
            pos_path=[(0, 0, 0), (1, 0, 0)],
            neg_path=[(0, 0.25, 0), (1, 0.25, 0)],
            coupling_ratio=100.0,
            max_skew_mm=0.0,
            avg_separation_mm=0.25,
            routing_time_s=0.001,
        )
        assert result.success
        assert len(result.pos_path) == 2
        assert result.error_message is None
