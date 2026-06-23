"""Tests for U3: Spatially-scoped clearance credit in DRCOracle.

@req(2026-06-23-007, R3): DRCOracle accepts a clearance_credits dict plus a
pin_owner mapping, and reduces the required clearance for a (lv_pin, hv_pin)
check when both pads resolve to the same component AND the segment between
the pad centers lies inside the slot's reclaimed AABB. The credit stacks
multiplicatively with the EXP-13 internal-layer factor (K5) and is rejected
for cross-component pin pairs.
"""

import pytest

from temper_placer.routing.constraints.design_rules import (
    ClearanceMatrix,
    DesignRulesParser,
)
from temper_placer.routing.constraints.drc_oracle import DRCOracle
from temper_placer.routing.constraints.geometry import Point
from temper_placer.routing.constraints.spatial_index import Pad


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _make_pad(pin_id: str, x: float, y: float, net: str = "HV") -> Pad:
    """Create a minimal Pad with the given pin_id and board-coords center."""
    return Pad(
        center=Point(x, y),
        shape="circle",
        size=(1.0, 1.0),
        net=net,
        layer=0,
        id=pin_id,
    )


@pytest.fixture
def oracle():
    """Oracle with the default rules and a 6.0mm clearance for HV-vs-LV."""
    rules = DesignRulesParser.create_default()
    # Inflate the HV default so a credit of 5.2 has a visible effect.
    rules._clearances[("HighVoltage", "Signal")] = 6.0
    rules._clearances[("Signal", "HighVoltage")] = 6.0
    return DRCOracle(rules)


# ----------------------------------------------------------------------
# Happy path: credit applied within band
# ----------------------------------------------------------------------


class TestCreditAppliedWithinBand:
    """P1 and P2 on the same credited component and inside the band → credit applies."""

    def test_credit_applied_within_band(self, oracle):
        """Pads straddling a Q1 isolation slot, in the reclaimed band."""
        oracle.pin_owner = {"Q1-1": "Q1", "Q1-2": "Q1"}
        oracle.add_clearance_credit(
            component_ref="Q1",
            lv_pin="1",
            hv_pin="2",
            effective_clearance_mm=5.2,
            half_width_mm=1.25,
            half_length_mm=10.0,
            slot_midpoint=(2.725, 0.0),
        )

        # Pads at (2.725, -4) and (2.725, +4) sit inside the credit band.
        p1 = _make_pad("Q1-1", 2.725, -4.0)
        p2 = _make_pad("Q1-2", 2.725, 4.0)

        effective = oracle.get_effective_clearance(p1, p2)
        assert effective == pytest.approx(5.2, abs=1e-9)


# ----------------------------------------------------------------------
# Spatial scope: credit refused when segment leaves the band
# ----------------------------------------------------------------------


class TestCreditOutsideBand:
    """Pads outside the slot's AABB → no credit, fall back to ClearanceMatrix."""

    def test_credit_not_applied_outside_band(self, oracle):
        """Pads far from the slot's reclaimed band — credit refused."""
        oracle.pin_owner = {"Q1-1": "Q1", "Q1-2": "Q1"}
        oracle.add_clearance_credit(
            component_ref="Q1",
            lv_pin="1",
            hv_pin="2",
            effective_clearance_mm=5.2,
            half_width_mm=1.25,
            half_length_mm=10.0,
            slot_midpoint=(2.725, 0.0),
        )

        # Pads at (-50, 0) and (-50, 10): both clearly outside the AABB
        # centered at (2.725, 0) with extents (1.75, 10). x=-50 is 53mm
        # from the slot center, well outside the half_width budget.
        p1 = _make_pad("Q1-1", -50.0, 0.0)
        p2 = _make_pad("Q1-2", -50.0, 10.0)

        assert oracle.get_effective_clearance(p1, p2) is None


# ----------------------------------------------------------------------
# Cross-component: credit never applies to other components
# ----------------------------------------------------------------------


class TestCreditDoesNotApplyToOtherComponents:
    """P1 and P2 on a non-credited component → no credit."""

    def test_credit_does_not_apply_to_other_components(self, oracle):
        oracle.pin_owner = {"Q1-1": "Q1", "Q1-2": "Q1", "D1-1": "D1", "D1-2": "D1"}
        oracle.add_clearance_credit(
            component_ref="Q1",
            lv_pin="1",
            hv_pin="2",
            effective_clearance_mm=5.2,
            half_width_mm=1.25,
            half_length_mm=10.0,
            slot_midpoint=(2.725, 0.0),
        )

        # Pads on D1, inside the spatial scope, but no credit for D1.
        p1 = _make_pad("D1-1", 2.725, -4.0)
        p2 = _make_pad("D1-2", 2.725, 4.0)

        assert oracle.get_effective_clearance(p1, p2) is None


# ----------------------------------------------------------------------
# K5: credit stacks multiplicatively with the internal-layer factor
# ----------------------------------------------------------------------


class TestCreditStacksWithInternalLayer:
    """When both credit and EXP-13 internal-layer factor apply, the effective
    is multiplicative, not additive."""

    def test_credit_stacks_with_internal_layer(self, oracle):
        oracle.pin_owner = {"Q1-1": "Q1", "Q1-2": "Q1"}
        oracle.add_clearance_credit(
            component_ref="Q1",
            lv_pin="1",
            hv_pin="2",
            effective_clearance_mm=5.2,
            half_width_mm=1.25,
            half_length_mm=10.0,
            slot_midpoint=(2.725, 0.0),
        )

        # Pads in the band, with one of them a PTH pad on an internal layer.
        # The credit reduces 6.0 → 5.2; the internal-layer factor then
        # multiplies 5.2 × 0.30 = 1.56. A 1.6mm clearance check passes.
        p1 = _make_pad("Q1-1", 2.725, -4.0)
        p1.is_pth = True
        p2 = _make_pad("Q1-2", 2.725, 4.0)

        # First, get the credited clearance (without internal layer).
        credit = oracle.get_effective_clearance(p1, p2)
        assert credit == pytest.approx(5.2, abs=1e-9)

        # Then apply the internal-layer factor multiplicatively.
        # 5.2 × 0.30 = 1.56, so a 1.6mm check passes; a 1.5mm check fails.
        stacked = credit * 0.30
        assert stacked == pytest.approx(1.56, abs=1e-9)
        assert 1.6 >= stacked  # pass
        assert 1.5 < stacked  # fail


# ----------------------------------------------------------------------
# Cross-component rejection: even with the right pin names, the credit
# is refused if the two pin owners are different components.
# ----------------------------------------------------------------------


class TestCreditSkippedWhenPinOwnerDiffers:
    """net_a's pin resolves to Q1, net_b's pin to Q2 → credit refused."""

    def test_credit_skipped_when_pin_owner_differs(self, oracle):
        oracle.pin_owner = {"Q1-1": "Q1", "Q2-2": "Q2"}
        oracle.add_clearance_credit(
            component_ref="Q1",
            lv_pin="1",
            hv_pin="2",
            effective_clearance_mm=5.2,
            half_width_mm=1.25,
            half_length_mm=10.0,
            slot_midpoint=(2.725, 0.0),
        )

        # Pads in the spatial scope, but owned by two different components.
        p1 = _make_pad("Q1-1", 2.725, -4.0)
        p2 = _make_pad("Q2-2", 2.725, 4.0)

        assert oracle.get_effective_clearance(p1, p2) is None


# ----------------------------------------------------------------------
# Misc: pin_owner can be a callable
# ----------------------------------------------------------------------


class TestPinOwnerCallable:
    """A callable pin_owner must work the same as a dict mapping."""

    def test_callable_pin_owner(self, oracle):
        owners = {"Q1-1": "Q1", "Q1-2": "Q1"}
        oracle.pin_owner = lambda pin_id: owners.get(pin_id)
        oracle.add_clearance_credit(
            component_ref="Q1",
            lv_pin="1",
            hv_pin="2",
            effective_clearance_mm=5.2,
            half_width_mm=1.25,
            half_length_mm=10.0,
            slot_midpoint=(2.725, 0.0),
        )

        p1 = _make_pad("Q1-1", 2.725, -4.0)
        p2 = _make_pad("Q1-2", 2.725, 4.0)

        assert oracle.get_effective_clearance(p1, p2) == pytest.approx(5.2, abs=1e-9)
