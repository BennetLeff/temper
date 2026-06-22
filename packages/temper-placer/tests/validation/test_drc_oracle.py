"""
Tests for DRCOracle: data conversion and batch placement evaluation.
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.validation.drc_oracle import (
    DRCOracle,
    build_constraint_set,
    build_placement_from_netlist,
    create_standard_drc_oracle,
)


def _make_minimal_context(n_components: int = 3) -> LossContext:
    """Build a minimal LossContext with n generic components."""
    components = []
    for i in range(n_components):
        c = Component(
            ref=f"U{i+1}",
            footprint="0805",
            bounds=(4.0, 3.0),
            net_class="Signal",
            pins=[Pin(f"p{j}", f"{j}", (float(j) * 1.5, 0)) for j in range(1, 3)],
        )
        components.append(c)
    netlist = Netlist(components=components, nets=[])
    board = Board(width=100, height=100)
    return LossContext.from_netlist_and_board(netlist, board)


# =============================================================================
# U1: Data Conversion Tests
# =============================================================================


class TestBuildPlacementFromNetlist:
    """Tests for build_placement_from_netlist conversion function."""

    def test_converts_all_components(self):
        """All netlist components appear in Placement."""
        context = _make_minimal_context(3)
        positions = jnp.array([[10.0, 10.0], [30.0, 30.0], [50.0, 50.0]])

        placement = build_placement_from_netlist(positions, context)

        assert len(placement.components) == 3
        assert "U1" in placement.components
        assert "U2" in placement.components
        assert "U3" in placement.components

    def test_component_attributes_are_correct(self):
        """ComponentPlacement has correct mapped attributes."""
        context = _make_minimal_context(2)
        positions = jnp.array([[15.0, 25.0], [45.0, 55.0]])

        placement = build_placement_from_netlist(positions, context)

        u1 = placement.get_component("U1")
        assert u1 is not None
        assert u1.ref == "U1"
        assert u1.footprint == "0805"
        assert u1.width == 4.0
        assert u1.height == 3.0
        assert u1.x == 15.0
        assert u1.y == 25.0
        assert u1.net_class == "Signal"
        assert u1.layer == "F.Cu"

    def test_all_pairs_count(self):
        """Placement.all_pairs returns correct number of pairs."""
        context = _make_minimal_context(3)
        positions = jnp.array([[10.0, 10.0], [20.0, 20.0], [30.0, 30.0]])

        placement = build_placement_from_netlist(positions, context)

        pairs = placement.all_pairs()
        assert len(pairs) == 3  # n*(n-1)/2 = 3*2/2 = 3

    def test_position_mapping(self):
        """Component positions match the provided positions array."""
        context = _make_minimal_context(2)
        positions = jnp.array([[12.5, 37.5], [62.5, 87.5]])

        placement = build_placement_from_netlist(positions, context)

        u1 = placement.get_component("U1")
        u2 = placement.get_component("U2")
        assert u1.x == 12.5
        assert u1.y == 37.5
        assert u2.x == 62.5
        assert u2.y == 87.5

    def test_get_component_returns_none_for_missing(self):
        """get_component returns None for unknown ref."""
        context = _make_minimal_context(2)
        positions = jnp.array([[10.0, 10.0], [20.0, 20.0]])

        placement = build_placement_from_netlist(positions, context)

        assert placement.get_component("NONEXISTENT") is None


class TestBuildConstraintSet:
    """Tests for build_constraint_set conversion function."""

    def test_empty_clearance_rules(self):
        """ConstraintSet with no clearance rules is empty."""
        context = _make_minimal_context(2)
        constraints = build_constraint_set(context)

        assert len(constraints.clearances) == 0

    def test_maps_clearance_rules(self):
        """ClearanceRules are correctly mapped to temper-drc format."""
        from temper_placer.losses.types import ClearanceRule as PlClearanceRule

        context = _make_minimal_context(2)
        rule = PlClearanceRule(
            net_class_a="ACMains",
            net_class_b="Signal",
            min_clearance=8.0,
        )
        # Patch in the rule (context is frozen, so use object.__setattr__)
        object.__setattr__(context, "clearance_rules", [rule])

        constraints = build_constraint_set(context)

        assert len(constraints.clearances) == 1
        assert constraints.clearances[0].from_class == "ACMains"
        assert constraints.clearances[0].to_class == "Signal"
        assert constraints.clearances[0].min_mm == 8.0

    def test_get_clearance_returns_expected_value(self):
        """ConstraintSet.get_clearance returns the correct value."""
        from temper_placer.losses.types import ClearanceRule as PlClearanceRule

        context = _make_minimal_context(2)
        rule = PlClearanceRule(
            net_class_a="HighVoltage",
            net_class_b="Signal",
            min_clearance=10.0,
        )
        object.__setattr__(context, "clearance_rules", [rule])

        constraints = build_constraint_set(context)

        # Both directions should match
        assert constraints.get_clearance("HighVoltage", "Signal") == 10.0
        assert constraints.get_clearance("Signal", "HighVoltage") == 10.0
        # Unmatched pair returns 0.0
        assert constraints.get_clearance("Signal", "Signal") == 0.0


# =============================================================================
# U2: DRCOracle Tests
# =============================================================================


class TestDRCOracleEvaluation:
    """Tests for DRCOracle.evaluate with real temper-drc checks."""

    def test_non_overlapping_placement_passes(self):
        """Non-overlapping placement returns passed=True for DRC checks."""
        context = _make_minimal_context(3)
        oracle = create_standard_drc_oracle(context)
        positions = jnp.array([[10.0, 10.0], [40.0, 40.0], [70.0, 70.0]])

        result = oracle.evaluate(positions, context, categories=["drc"])

        assert result.passed is True
        assert result.error_count == 0
        assert result.critical_count == 0

    def test_overlapping_placement_fails(self):
        """Overlapping components produce DRC failures."""
        context = _make_minimal_context(3)
        oracle = create_standard_drc_oracle(context)
        # U1 and U2 overlap (same position)
        positions = jnp.array([[10.0, 10.0], [11.0, 10.0], [70.0, 70.0]])

        result = oracle.evaluate(positions, context)

        assert result.passed is False
        assert result.total_penalty > 0
        assert any(
            i.check_name == "drc_component_overlap" for i in result.all_issues
        )

    def test_different_placements_produce_different_results(self):
        """Two different placements produce different penalty values."""
        context = _make_minimal_context(3)
        oracle = create_standard_drc_oracle(context)

        pos_good = jnp.array([[10.0, 10.0], [40.0, 40.0], [70.0, 70.0]])
        pos_bad = jnp.array([[10.0, 10.0], [12.0, 10.0], [70.0, 70.0]])

        result_good = oracle.evaluate(pos_good, context)
        result_bad = oracle.evaluate(pos_bad, context)

        assert result_bad.total_penalty > result_good.total_penalty

    def test_category_filtering(self):
        """Category filter limits which checks run."""
        context = _make_minimal_context(3)
        oracle = create_standard_drc_oracle(context)
        positions = jnp.array([[10.0, 10.0], [11.0, 10.0], [70.0, 70.0]])

        # Run only DRC checks (skip safety, EMC, ERC)
        result_drc_only = oracle.evaluate(positions, context, categories=["drc"])

        # Run all checks
        result_all = oracle.evaluate(positions, context, categories=None)

        # DRC-only should have fewer checks run
        assert result_drc_only.total_checks <= result_all.total_checks

    def test_evaluate_placement_method(self):
        """evaluate_placement works with pre-built Placement."""
        context = _make_minimal_context(2)
        oracle = create_standard_drc_oracle(context)
        positions = jnp.array([[10.0, 10.0], [40.0, 40.0]])

        placement = build_placement_from_netlist(positions, context)
        result = oracle.evaluate_placement(placement, categories=["drc"])

        assert result.passed is True
        assert result.total_checks > 0
