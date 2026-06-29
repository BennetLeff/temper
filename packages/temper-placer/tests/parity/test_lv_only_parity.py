"""
Parity test for the U1 ghost-pad injection: an LV-only board must
produce bit-identical placements to a pre-U1 (no-injection) run.

NFR4 / SM4: this is the regression anchor for the U1 change.
"""

from __future__ import annotations

from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import PlacementConstraints

# Frozen LV-only board fixture.
_LV_NETLIST = Netlist(
    components=[
        Component(
            ref="C1",
            footprint="0603",
            bounds=(2.0, 2.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
        ),
        Component(
            ref="C2",
            footprint="0603",
            bounds=(2.0, 2.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="GND")],
        ),
        Component(
            ref="R1",
            footprint="0603",
            bounds=(2.0, 2.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
        ),
    ],
    nets=[
        Net(name="VCC", pins=[("C1", "1"), ("R1", "1")], net_class="Power"),
        Net(name="GND", pins=[("C2", "1")], net_class="Ground"),
    ],
)

_LV_DESIGN_RULES = DesignRules(
    net_classes={
        "Power": NetClassRules(
            name="Power", trace_width=0.25, clearance=0.2, dru_priority=10,
            safety_category="LV",
        ),
        "Ground": NetClassRules(
            name="Ground", trace_width=0.25, clearance=0.2, dru_priority=20,
            safety_category="LV",
        ),
    },
    net_class_assignments={"VCC": "Power", "GND": "Ground"},
)


def _make_state() -> BoardState:
    """Build the frozen BoardState for the LV-only parity fixture."""
    slots = [(float(x), float(y)) for x in range(0, 100, 5) for y in range(0, 100, 5)]
    return BoardState(
        netlist=_LV_NETLIST,
        component_zone_map=frozenset(
            [(c.ref, "Signal") for c in _LV_NETLIST.components]
        ),
        zone_slots=frozenset([("Signal", tuple(slots))]),
        design_rules=_LV_DESIGN_RULES,
    )


def test_parity_lv_only_bit_identical():
    """A pre-U1 run and a U1 run on the same LV-only board must match exactly."""
    state = _make_state()
    constraints = PlacementConstraints()
    constraints.placement_priority = {"auto": {"method": "auto"}}

    # Pre-U1: design_rules=None means no ghost-pad ring.
    stage_off = PhasedComponentAssignmentStage(constraints, design_rules=None)
    result_off = dict(stage_off.run(state).placements)

    # U1: design_rules provided; no HV ring because the board is LV-only.
    stage_on = PhasedComponentAssignmentStage(constraints, design_rules=_LV_DESIGN_RULES)
    result_on = dict(stage_on.run(state).placements)

    assert result_on == result_off, (
        f"Parity anchor broken:\n  pre-U1: {result_off}\n  U1: {result_on}"
    )


def test_parity_lv_only_idempotent():
    """Running the placer twice on the LV-only board yields identical placements."""
    state = _make_state()
    constraints = PlacementConstraints()
    constraints.placement_priority = {"auto": {"method": "auto"}}
    stage = PhasedComponentAssignmentStage(constraints, design_rules=_LV_DESIGN_RULES)
    a = dict(stage.run(state).placements)
    b = dict(stage.run(state).placements)
    assert a == b
