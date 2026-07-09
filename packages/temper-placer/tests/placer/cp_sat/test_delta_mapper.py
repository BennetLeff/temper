"""U3: DeltaMapper unit tests.

Covers all seven ViolationType -> PCL constraint mappings,
including the delta tightening (CLEARANCE +0.1 mm) and
the LOOP_INDUCTANCE 5%/round ratchet.
"""

from __future__ import annotations

import pytest

from temper_placer.placer.cp_sat.delta_mapper import DeltaMapper
from temper_placer.placer.cp_sat.gates import Violation, ViolationType

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _delta_constraint_type(delta):
    """Return the class name of the constraint inside a ConstraintDelta."""
    return type(delta.constraint).__name__


# ---------------------------------------------------------------------------
# CLEARANCE -> SeparatedConstraint
# ---------------------------------------------------------------------------


def test_clearance_maps_to_separated():
    v = Violation(
        type=ViolationType.CLEARANCE,
        components=("Q1", "Q2"),
        severity=5.0,
        threshold=6.0,
        description="Clearance too small",
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert _delta_constraint_type(delta) == "SeparatedConstraint"
    assert delta.constraint.min_distance_mm == 5.1  # severity + 0.1
    assert delta.constraint.tier.value == 1  # HARD
    assert delta.priority == 5


def test_clearance_requires_two_components():
    v = Violation(
        type=ViolationType.CLEARANCE,
        components=("Q1",),
        severity=5.0,
    )
    assert DeltaMapper.map(v) is None


# ---------------------------------------------------------------------------
# UNROUTED -> AnchoredConstraint
# ---------------------------------------------------------------------------


def test_unrouted_maps_to_anchored():
    v = Violation(
        type=ViolationType.UNROUTED,
        nets=("GATE_H",),
        components=("Q1",),
        context={"region": (-5.0, -5.0, 5.0, 5.0)},
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert _delta_constraint_type(delta) == "AnchoredConstraint"
    assert delta.constraint.component == "Q1"
    assert delta.constraint.region == (-5.0, -5.0, 5.0, 5.0)
    assert delta.priority == 15


def test_unrouted_without_component_returns_none():
    v = Violation(
        type=ViolationType.UNROUTED,
        nets=("GATE_H",),
        components=(),
    )
    assert DeltaMapper.map(v) is None


def test_unrouted_fallback_region():
    v = Violation(
        type=ViolationType.UNROUTED,
        nets=("GATE_H",),
        components=("Q1",),
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert delta.constraint.region == (-10.0, -10.0, 10.0, 10.0)


# ---------------------------------------------------------------------------
# LOOP_INDUCTANCE -> LoopAreaConstraint
# ---------------------------------------------------------------------------


def test_loop_inductance_maps_to_loop_area():
    v = Violation(
        type=ViolationType.LOOP_INDUCTANCE,
        severity=2500.0,
        threshold=2000.0,
        context={"loop": "commutation", "max_area_mm2": 2000.0},
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert _delta_constraint_type(delta) == "LoopAreaConstraint"
    assert delta.constraint.loop_name == "commutation"
    # severity * 0.95 = 2375, max_area * 0.95 = 1900 -> min = 1900
    assert delta.constraint.max_area_mm2 == 1900.0
    assert delta.priority == 30


def test_loop_inductance_ratchet_same_id():
    """Two LOOP_INDUCTANCE violations on the same loop produce same id."""
    v1 = Violation(
        type=ViolationType.LOOP_INDUCTANCE,
        severity=2500.0,
        threshold=2000.0,
        context={"loop": "commutation", "max_area_mm2": 2000.0},
    )
    v2 = Violation(
        type=ViolationType.LOOP_INDUCTANCE,
        severity=2000.0,
        threshold=2000.0,
        context={"loop": "commutation", "max_area_mm2": 2000.0},
    )
    d1 = DeltaMapper.map(v1)
    d2 = DeltaMapper.map(v2)
    assert d1.constraint.id == d2.constraint.id == "loop_commutation"
    # Second one is tighter (2000*0.95=1900 vs 2375 min 1900=1900)
    assert d2.constraint.max_area_mm2 == 1900.0


# ---------------------------------------------------------------------------
# THERMAL -> SeparatedConstraint
# ---------------------------------------------------------------------------


def test_thermal_maps_to_separated():
    v = Violation(
        type=ViolationType.THERMAL,
        components=("Q1", "U_MCU"),
        severity=100.0,
        threshold=50.0,
        description="Pour area too small",
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert _delta_constraint_type(delta) == "SeparatedConstraint"
    assert delta.constraint.min_distance_mm == 51.0  # threshold + 1.0
    assert delta.constraint.tier.value == 1  # HARD
    assert delta.priority == 10


def test_thermal_requires_two_components():
    v = Violation(
        type=ViolationType.THERMAL,
        components=("Q1",),
    )
    assert DeltaMapper.map(v) is None


# ---------------------------------------------------------------------------
# CREEPAGE -> SeparatedConstraint
# ---------------------------------------------------------------------------


def test_creepage_maps_to_separated():
    v = Violation(
        type=ViolationType.CREEPAGE,
        nets=("DC_BUS+", "+3V3"),
        severity=5.0,
        threshold=6.0,
        description="IEC creepage",
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert _delta_constraint_type(delta) == "SeparatedConstraint"
    assert delta.constraint.min_distance_mm == 6.0
    assert delta.constraint.tier.value == 1  # HARD
    assert delta.priority == 5


def test_creepage_requires_two_nets():
    v = Violation(
        type=ViolationType.CREEPAGE,
        nets=("DC_BUS+",),
    )
    assert DeltaMapper.map(v) is None


# ---------------------------------------------------------------------------
# VIA_COUNT -> KeepoutConstraint
# ---------------------------------------------------------------------------


def test_via_count_maps_to_keepout():
    v = Violation(
        type=ViolationType.VIA_COUNT,
        components=("Q1",),
        severity=3.0,
        threshold=9.0,
        context={"device": "Q1"},
        description="Too few thermal vias",
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert _delta_constraint_type(delta) == "KeepoutConstraint"
    assert delta.constraint.zone_name == "keepout_vias_Q1"
    assert delta.priority == 20


# ---------------------------------------------------------------------------
# SLOP -> KeepoutConstraint
# ---------------------------------------------------------------------------


def test_slop_maps_to_keepout():
    v = Violation(
        type=ViolationType.SLOP,
        nets=("GATE_H",),
        severity=2.0,
        context={
            "artifact_type": "hairpin",
            "artifacts": [
                {
                    "net_name": "GATE_H",
                    "position": (10.0, 20.0),
                    "description": "Hairpin turn",
                }
            ],
        },
        description="Slop detected",
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert _delta_constraint_type(delta) == "KeepoutConstraint"
    assert "SLOP_hairpin_GATE_H" in delta.constraint.zone_name
    assert delta.priority == 30


def test_slop_fallback_zone_name():
    v = Violation(
        type=ViolationType.SLOP,
        severity=1.0,
        description="Generic slop",
    )
    delta = DeltaMapper.map(v)
    assert delta is not None
    assert _delta_constraint_type(delta) == "KeepoutConstraint"


# ---------------------------------------------------------------------------
# Unmapped types -> None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vtype",
    [
        ViolationType.SHORTING,
        ViolationType.MASK_BRIDGE,
        ViolationType.EDGE_CLEARANCE,
        ViolationType.REFERENCE_PLANE_SPLIT,
        ViolationType.CURRENT_DENSITY,
        ViolationType.OCTILINEAR,
    ],
)
def test_unmapped_type_returns_none(vtype):
    v = Violation(type=vtype, description="test")
    assert DeltaMapper.map(v) is None
