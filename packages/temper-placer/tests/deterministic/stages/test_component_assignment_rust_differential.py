"""Differential test: component_assignment greedy kernel, Rust vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The greedy
slot-assignment compute of ``deterministic/stages/component_assignment.py``
moves to the ``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_leaves``); the Python module
becomes a delegation shim (the GEOS domain filter stays Python and is
precomputed into the `domain_ok` predicate). The pre-migration
implementation is pinned VERBATIM as the oracle
(``_component_assignment_py_oracle.py``).

R1a: the placements dict compares bit-identically via ``canon`` — fixed
placements first, largest-first ordering, per-zone slot availability, the
cross-zone fallback, wirelength-first-slot-minimum ties, footprint-radius
reservation, and the domain filter.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._component_assignment_py_oracle as _oracle
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from tests.core._contract_canon import canon

_RS = _tdb.deterministic_leaves


def _pin(name, number, position):
    return Pin(name=name, number=number, position=position)


def _comp(ref, bounds, pins=None, sheetpath=None):
    return Component(
        ref=ref, footprint="FP", bounds=bounds,
        pins=pins or [_pin("1", "1", (0, 0))], sheetpath=sheetpath,
    )


def _netlist(components, net_pins):
    nets = [Net(name=name, pins=list(pins)) for name, pins in net_pins]
    return Netlist(nets=nets, components=components)


def _assert_equal(netlist, zone_map, zone_slots, fixed=None, domain_ok=None,
                  slot_spacing=12.0, oracle_domains=None):
    fixed = fixed or {}
    dom_ok = domain_ok or {}
    exp = _oracle.assign_components_to_slots(
        netlist, zone_map, zone_slots,
        domain_for_ref=oracle_domains[0] if oracle_domains else None,
        domain_regions=oracle_domains[1] if oracle_domains else None,
        slot_spacing=slot_spacing,
        fixed_placements=fixed,
    )
    got = _RS.assign_components_to_slots(netlist, zone_map, zone_slots, fixed, dom_ok, slot_spacing)
    assert canon(exp) == canon(got), f"exp={exp} got={got}"


def test_basic_assignment():
    comps = [
        _comp("R1", (4.0, 2.0)),
        _comp("R2", (4.0, 2.0)),
        _comp("C1", (2.0, 1.0)),
    ]
    nl = _netlist(comps, [("N1", [("R1", "1"), ("R2", "1")])])
    zone_map = {"R1": "Signal", "R2": "Signal", "C1": "Signal"}
    zone_slots = {"Signal": ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0), (15.0, 15.0))}
    _assert_equal(nl, zone_map, zone_slots)


def test_largest_first_sort():
    """Larger footprints are placed first (blocking radius)."""
    comps = [
        _comp("SMALL", (1.0, 1.0)),
        _comp("BIG", (10.0, 8.0)),
        _comp("MED", (4.0, 4.0)),
    ]
    nl = _netlist(comps, [])
    zone_map = {c.ref: "Signal" for c in comps}
    zone_slots = {"Signal": ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0))}
    _assert_equal(nl, zone_map, zone_slots)


def test_fixed_placements():
    comps = [_comp("R1", (4.0, 2.0)), _comp("R2", (4.0, 2.0))]
    nl = _netlist(comps, [])
    zone_map = {"R1": "Signal", "R2": "Signal"}
    zone_slots = {"Signal": ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0))}
    fixed = {"R1": (2.0, 2.0)}
    _assert_equal(nl, zone_map, zone_slots, fixed=fixed)
    exp = _oracle.assign_components_to_slots(
        nl, zone_map, zone_slots, slot_spacing=12.0, fixed_placements={"R1": (2.0, 2.0)}
    )
    assert exp["R1"] == (2.0, 2.0)


def test_fixed_placements_reserves_slots():
    """A fixed placement reserves slots in its footprint radius."""
    comps = [_comp("BIG", (10.0, 8.0)), _comp("R2", (4.0, 2.0))]
    nl = _netlist(comps, [])
    zone_map = {"BIG": "Signal", "R2": "Signal"}
    zone_slots = {"Signal": ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0))}
    fixed = {"BIG": (0.0, 0.0)}
    exp = _oracle.assign_components_to_slots(
        nl, zone_map, zone_slots, slot_spacing=12.0, fixed_placements={"BIG": (0.0, 0.0)}
    )
    got = _RS.assign_components_to_slots(nl, zone_map, zone_slots, fixed, {}, 12.0)
    assert canon(exp) == canon(got)
    # The reservation must push R2 off the (0,0) / (5,5) slots.
    assert got["R2"] == (10.0, 10.0)


def test_reservation_radius_band():
    """A slot at distance in the (radius, radius+1] band is NOT reserved by
    `dist <= radius` but IS by a +1.0 over-reservation — pinning the exact
    radius boundary (BIG(10,8): radius = sqrt(164)/2 + 1 ~ 7.403; the slot
    at (8,0) is at distance 8.0)."""
    comps = [_comp("BIG", (10.0, 8.0)), _comp("R2", (4.0, 2.0))]
    nl = _netlist(comps, [])
    zone_map = {"BIG": "Signal", "R2": "Signal"}
    zone_slots = {"Signal": ((0.0, 0.0), (8.0, 0.0), (10.0, 10.0))}
    fixed = {"BIG": (0.0, 0.0)}
    exp = _oracle.assign_components_to_slots(
        nl, zone_map, zone_slots, slot_spacing=12.0, fixed_placements={"BIG": (0.0, 0.0)}
    )
    got = _RS.assign_components_to_slots(nl, zone_map, zone_slots, fixed, {}, 12.0)
    assert canon(exp) == canon(got)
    assert got["R2"] == (8.0, 0.0)


def test_zone_fallback():
    """When a zone is exhausted, the kernel falls back to other zones."""
    comps = [_comp("A", (4.0, 2.0)), _comp("B", (4.0, 2.0)), _comp("C", (4.0, 2.0))]
    nl = _netlist(comps, [])
    zone_map = {"A": "HV", "B": "HV", "C": "HV"}
    zone_slots = {
        "HV": ((0.0, 0.0),),
        "Signal": ((5.0, 5.0), (10.0, 10.0)),
    }
    _assert_equal(nl, zone_map, zone_slots)


def test_empty_slots_skipped():
    """No available slots anywhere -> the component is skipped."""
    comps = [_comp("A", (4.0, 2.0)), _comp("B", (4.0, 2.0))]
    nl = _netlist(comps, [])
    zone_map = {"A": "HV", "B": "HV"}
    zone_slots = {}
    _assert_equal(nl, zone_map, zone_slots)
    exp = _oracle.assign_components_to_slots(nl, zone_map, zone_slots, slot_spacing=12.0)
    assert exp == {}


def test_wirelength_binds_same_net():
    """A component on a net with an already-placed component scores slots by
    HPWL: the closest slot to the placed partner wins."""
    comps = [_comp("U1", (4.0, 2.0)), _comp("R1", (1.0, 1.0))]
    nl = _netlist(comps, [("NET", [("U1", "1"), ("R1", "1")])])
    zone_map = {"U1": "Signal", "R1": "Signal"}
    zone_slots = {
        "Signal": ((0.0, 0.0), (0.0, 50.0), (50.0, 0.0), (50.0, 50.0)),
    }
    fixed = {"U1": (50.0, 50.0)}
    exp = _oracle.assign_components_to_slots(
        nl, zone_map, zone_slots, slot_spacing=12.0, fixed_placements={"U1": (50.0, 50.0)}
    )
    got = _RS.assign_components_to_slots(nl, zone_map, zone_slots, fixed, {}, 12.0)
    assert canon(exp) == canon(got)
    # Closest slot to U1 at (50,50) is (50,50)-adjacent: (50,0) is dist 50.
    assert got["R1"] == exp["R1"]


def test_no_bounds_uses_half_spacing():
    """A component without bounds defaults its footprint radius to
    slot_spacing / 2."""
    comps = [_comp("X", None)]
    nl = _netlist(comps, [])
    zone_map = {"X": "Signal"}
    zone_slots = {"Signal": ((0.0, 0.0), (20.0, 0.0))}
    _assert_equal(nl, zone_map, zone_slots, slot_spacing=10.0)


def test_int_bounds_bit_exact():
    """Integer bounds compute `w**2` as int-pow (then float sqrt); the
    result is bit-identical to the oracle's `math.sqrt`."""
    comps = [_comp("I", (3, 4))]
    nl = _netlist(comps, [])
    zone_map = {"I": "Signal"}
    zone_slots = {"Signal": ((0.0, 0.0), (10.0, 10.0))}
    _assert_equal(nl, zone_map, zone_slots)
    exp = _oracle._get_footprint_radius(_comp("I", (3, 4)), 12.0)
    got = _RS.assign_components_to_slots(nl, zone_map, zone_slots, {}, {}, 12.0)
    assert got["I"] == (0.0, 0.0)
    # 3**2 + 4**2 = 25, sqrt = 5.0, /2 + 1 = 3.5; both (0,0),(10,10) are within 3.5 of (0,0)... verify via hex on the oracle helper.
    assert _oracle._get_footprint_radius(_comp("I", (3, 4)), 12.0) == 3.5


def test_domain_filter_nfr6_noop():
    """An empty domain_ok (partition disabled) is a no-op — NFR6."""
    comps = [_comp("A", (4.0, 2.0)), _comp("B", (4.0, 2.0))]
    nl = _netlist(comps, [])
    zone_map = {"A": "Signal", "B": "Signal"}
    zone_slots = {"Signal": ((0.0, 0.0), (5.0, 5.0))}
    _assert_equal(nl, zone_map, zone_slots)


def test_domain_filter_via_shim():
    """End-to-end: the GEOS domain filter runs in the shim, the greedy
    assignment in Rust — the combined placements match the oracle."""
    from shapely.geometry import Polygon

    from temper_placer.deterministic.stages.component_assignment import (
        ComponentAssignmentStage,
    )

    comps = [
        _comp("HV1", (4.0, 2.0)),
        _comp("HV2", (4.0, 2.0)),
        _comp("LV1", (4.0, 2.0)),
    ]
    nl = _netlist(comps, [])
    zone_map = {"HV1": "HV", "HV2": "HV", "LV1": "LV"}
    zone_slots = {
        "HV": ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0)),
        "LV": ((50.0, 50.0), (55.0, 55.0), (60.0, 60.0)),
    }
    # A domain map that confines HV components to the x<=6 half and LV to x>=49.
    domain_for_ref = {"HV1": "HV_edge", "HV2": "HV_edge", "LV1": "LV_interior"}
    hv_region = Polygon([(0, -10), (6, -10), (6, 70), (0, 70)])
    lv_region = Polygon([(49, -10), (70, -10), (70, 70), (49, 70)])
    domain_regions = {"HV_edge": hv_region, "LV_interior": lv_region}

    stage = ComponentAssignmentStage(slot_spacing=12.0)
    got = stage._assign_components_to_slots(nl, zone_map, zone_slots, domain_for_ref, domain_regions)

    exp = _oracle.assign_components_to_slots(
        nl, zone_map, zone_slots,
        domain_for_ref=domain_for_ref, domain_regions=domain_regions, slot_spacing=12.0,
    )
    assert canon(exp) == canon(got)
    # The HV filter excludes (10,10); LV filter excludes (50,50)/(55,55)/(60,60)
    # is NOT excluded (all within LV region) — so LV1 goes to the first LV slot.
    assert got["HV1"] == (0.0, 0.0)
    assert got["HV2"] == (5.0, 5.0)
    assert got["LV1"] == (50.0, 50.0)
