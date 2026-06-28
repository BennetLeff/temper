"""PBT: Router V6 topological correctness invariants.

Property-based tests for topological correctness invariants using
Hypothesis-generated inputs from the shared ``router_v6_property_strategies``.

Tests verify:
  R6: SAT solution consistency — unique net names, every pin has a net
  R7: Channel capacity — component bounds are positive and finite
  R8: Escape via completeness — ``generate_escape_vias`` returns a list

SAT solver and escape-via placement require real pipeline data,
so these tests focus on structural invariants that CAN be verified
with strategy-generated inputs.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings

from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.escape_via_generator import generate_escape_vias

from .router_v6_property_strategies import (
    component_list,
    netlist,
    parsed_pcb,
)


@pytest.mark.property
@given(nl=netlist())
@settings(max_examples=100, deadline=30000)
def test_every_net_name_is_unique(nl):
    """R6: Every net name is unique within a generated Netlist."""
    names = [net.name for net in nl.nets]
    assert len(names) == len(set(names)), (
        f"Duplicate net names detected: {len(names)} names, {len(set(names))} unique"
    )


@pytest.mark.property
@given(comps=component_list())
@settings(max_examples=100, deadline=30000)
def test_every_pin_has_net_assignment(comps):
    """R6: Every pin on generated components has a net assignment."""
    for comp in comps:
        for pin in comp.pins:
            assert pin.net is not None, (
                f"Pin {pin.name} on {comp.ref} has no net assignment"
            )


@pytest.mark.property
@given(comps=component_list())
@settings(max_examples=100, deadline=30000)
def test_component_bounds_positive_and_finite(comps):
    """R7: Component bounds are positive and finite."""
    for comp in comps:
        w, h = comp.bounds
        assert w > 0.0 and math.isfinite(w), (
            f"{comp.ref} width={w} invalid"
        )
        assert h > 0.0 and math.isfinite(h), (
            f"{comp.ref} height={h} invalid"
        )


@pytest.mark.property
@given(pcb=parsed_pcb())
@settings(max_examples=100, deadline=30000)
def test_net_class_assignments_cover_net_classes(pcb):
    """R7: Every net class assignment in DesignRules references a defined net class."""
    assignments = pcb.design_rules.net_class_assignments
    net_classes = pcb.design_rules.net_classes
    for net_name, class_name in assignments.items():
        assert class_name in net_classes, (
            f"Net '{net_name}' assigned to undefined class '{class_name}'; "
            f"available: {sorted(net_classes.keys())}"
        )


@pytest.mark.property
@given(pcb=parsed_pcb())
@settings(max_examples=100, deadline=30000)
def test_generate_escape_vias_returns_list(pcb):
    """R8: ``generate_escape_vias`` returns a list (can be empty, never None)."""
    candidates = [c for c in pcb.components if c.pins]
    if not candidates:
        return

    comp = candidates[0]
    dp = DensePackage(
        component=comp,
        pin_count=len(comp.pins),
        pitch_mm=0.5,
        package_type="BGA",
        requires_escape=True,
    )

    for strategy in ("dog-bone", "via-in-pad"):
        result = generate_escape_vias(dp, pcb.design_rules, strategy=strategy)
        assert isinstance(result, list), (
            f"generate_escape_vias(strategy={strategy!r}) returned "
            f"{type(result).__name__}, expected list"
        )
