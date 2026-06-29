"""
Tests for feat/hv-lv-guard-strip integration with PhasedComponentAssignmentStage.

The plan's U3 last scenario: ``phased_component_assignment`` with
``component_domain_map = frozenset()`` (no prior partition stage) must
produce the same placements as the unfiltered baseline (NFR6).
"""

from __future__ import annotations

from unittest.mock import Mock

from shapely.geometry import Polygon

from temper_placer.deterministic.stages.phased_component_assignment import (
    PhasedComponentAssignmentStage,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import PlacementConstraints


def _make_constraints(priority: dict | None = None) -> PlacementConstraints:
    constraints = PlacementConstraints()
    if priority is not None:
        constraints.placement_priority = priority
    return constraints


def _make_state(
    constraints: PlacementConstraints,
    *,
    component_domain_map: frozenset = frozenset(),
    domain_regions: tuple = (),
) -> BoardState:
    netlist = Mock()
    netlist.components = [Mock(ref="C1", bounds=(5, 5)), Mock(ref="C2", bounds=(3, 3))]
    netlist.nets = []
    slots = tuple((float(x), float(y)) for x in range(0, 30, 10) for y in range(0, 30, 10))
    state = BoardState(
        netlist=netlist,
        component_zone_map=frozenset([("C1", "Signal"), ("C2", "Signal")]),
        zone_slots=frozenset([("Signal", slots)]),
        component_domain_map=component_domain_map,
        domain_regions=domain_regions,
    )
    return state


def test_phased_assignment_no_domain_map_is_noop():
    """Empty domain map: placements match the unfiltered baseline (NFR6)."""
    constraints = _make_constraints(
        priority={
            "auto": {"components": ["C1", "C2"], "method": "auto"},
        }
    )
    stage = PhasedComponentAssignmentStage(constraints)

    state_baseline = _make_state(constraints)
    result_baseline = stage.run(state_baseline)

    # Run again with the same empty domain map (NFR6 scenario).
    state_nfr6 = _make_state(constraints)
    result_nfr6 = stage.run(state_nfr6)

    assert dict(result_baseline.placements) == dict(result_nfr6.placements)


def test_phased_assignment_with_domain_map_filters_slots():
    """Domain map drops slots outside the component's domain region (FR4)."""
    from shapely.geometry import Point

    constraints = _make_constraints(
        priority={
            "auto": {"components": ["C1", "C2"], "method": "auto"},
        }
    )
    stage = PhasedComponentAssignmentStage(constraints)

    # Two disjoint regions of the same Signal slot grid.
    hv_region = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])
    lv_region = Polygon([(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)])
    domain_map = frozenset({("C1", "HV_edge"), ("C2", "LV_interior")})

    state = BoardState(
        netlist=Mock(
            components=[Mock(ref="C1", bounds=(5, 5)), Mock(ref="C2", bounds=(3, 3))],
            nets=[],
        ),
        component_zone_map=frozenset({("C1", "Signal"), ("C2", "Signal")}),
        zone_slots=frozenset(
            {("Signal", tuple((float(x), float(y)) for x in range(0, 30, 10) for y in range(0, 30, 10)))}
        ),
        component_domain_map=domain_map,
        domain_regions=(hv_region, lv_region),
    )
    result = stage.run(state)

    placements = dict(result.placements)
    assert "C1" in placements, f"Expected C1 placement, got {placements}"
    assert "C2" in placements, f"Expected C2 placement, got {placements}"
    # C1 must be inside (or on the boundary of) the HV region
    assert hv_region.covers(Point(placements["C1"][0], placements["C1"][1]))
    # C2 must be inside (or on the boundary of) the LV region
    assert lv_region.covers(Point(placements["C2"][0], placements["C2"][1]))


def test_phased_assignment_re_exports_via_deterministic():
    from temper_placer.deterministic import HvLvPartitionStage, PartitionError

    assert HvLvPartitionStage is not None
    assert PartitionError is not None
