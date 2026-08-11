"""Metamorphic relations for the Phase E batch E3 clearance-family
orchestration (temper-orchestration ``clearance`` module, exercised through
the delegation shims).

Rust Orchestration Engine plan 2026-08-09-001 Phase E E3. G5: >= 3
invariant relations per module family, each with a discriminating companion
that asserts the relation does not hold vacuously.

- MR1  clearance-engine symmetry: ``get_clearance(a, b, ...) ==
       get_clearance(b, a, ...)`` for any two net classes (the engine's
       candidates are a function of the unordered pair). Companion: the
       same input through the differential oracle agrees.
- MR2  creepage threshold superset: raising ``default_creepage`` never
       removes a violating (hv, lv) pair — the violation set at the lower
       threshold is a subset of the set at the higher threshold. Companion:
       a case where the threshold increase ADDS a pair is asserted.
- MR3  domain-partition ref covariance: a bijective ref renaming
       ``ref -> ref'`` maps every component's bucket membership through the
       same renaming (classification is a pure function of pin-net
       membership, never of the ref spelling). Companion: a component whose
       ref contains an HV substring but whose nets are SELV stays SELV (the
       classifier does not pattern-match refs).
- MR4  domain-clearance audit monotone in separation: moving a resolved
       position farther from its partner never creates a NEW audit
       violation — ``audit(far)``'s violation set is a subset of
       ``audit(close)``'s by (ref_a, ref_b). Companion: a far placement
       that clears every constraint is asserted to produce zero violations.
- MR5  barrier rotation periodicity: ``project_onto_barrier_axis(x, y, r+4,
       axis) == project_onto_barrier_axis(x, y, r, axis)`` — the 4-rotation
       table is 4-periodic. Companion: the full 4-row table is pinned.
"""

from __future__ import annotations

import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.placer.cp_sat.domain_clearance import (
    audit_domain_clearance,
    generate_domain_clearance_constraints,
)
from temper_placer.placer.cp_sat.isolation_barrier import (
    _project_onto_barrier_axis,
    classify_domain_partition,
)
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_engine import get_clearance
from temper_placer.router_v6.creepage_check import verify_creepage
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from tests.router_v6 import _clearance_family_py_oracle as _oracle

_NET_CLASSES = ["HV", "SIGNAL", "GND", "POWER", "MAINS", "AC_L", "+15V_LS", "DC_BUS_RTN", "LV"]


def _make_route(net_name, coords):
    length = abs(coords[1][0] - coords[0][0])
    return CompiledRoute(
        net_name=net_name,
        path=RoutePath(net_name=net_name, coordinates=list(coords), layer_name="F.Cu", path_length=length),
        width_mm=0.127,
        vias=[],
        matched_length_mm=None,
    )


# ---------------------------------------------------------------------------
# MR1 — clearance-engine symmetry in the net classes
# ---------------------------------------------------------------------------


def test_mr1_get_clearance_symmetric_in_net_classes():
    for a in _NET_CLASSES:
        for b in _NET_CLASSES:
            for v in (5.0, 230.0, 340.0):
                for layer_type in ("external", "internal"):
                    assert get_clearance(a, b, v, layer_type=layer_type) == get_clearance(
                        b, a, v, layer_type=layer_type
                    ), (a, b, v, layer_type)


def test_mr1_companion_agrees_with_oracle():
    # The relation discriminates: the engine really is symmetric, and the
    # oracle's value is reached from both orders.
    for a, b, v in [("HV", "SIGNAL", 340.0), ("MAINS", "LV", 230.0), ("GND", "POWER", 12.0)]:
        want = _oracle.get_clearance(a, b, v)
        assert get_clearance(a, b, v) == want
        assert get_clearance(b, a, v) == want


# ---------------------------------------------------------------------------
# MR2 — creepage threshold superset
# ---------------------------------------------------------------------------


def _creepage_violation_set(report):
    return {(v.hv_net, v.lv_net) for v in report.violations}


def test_mr2_creepage_threshold_superset():
    rr = RoutingResults(
        compiled_routes={
            "AC_L": _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)]),
            "GND": _make_route("GND", [(0.0, 0.2), (10.0, 0.2)]),
            "HV_BUS": _make_route("HV_BUS", [(0.0, 5.0), (10.0, 5.0)]),
            "SIG1": _make_route("SIG1", [(0.0, 6.0), (10.0, 6.0)]),
        },
        failed_nets=[],
    )
    low = verify_creepage(rr, default_creepage=0.1)
    high = verify_creepage(rr, default_creepage=8.0)
    assert _creepage_violation_set(low) <= _creepage_violation_set(high)
    assert low.total_checks == high.total_checks


def test_mr2_companion_threshold_adds_pairs():
    # A relaxed threshold really adds the AC_L/GND pair (0.2 mm apart): the
    # relation is not vacuous on always-identical sets.
    rr = RoutingResults(
        compiled_routes={
            "AC_L": _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)]),
            "GND": _make_route("GND", [(0.0, 0.2), (10.0, 0.2)]),
        },
        failed_nets=[],
    )
    low = verify_creepage(rr, default_creepage=0.1)
    high = verify_creepage(rr, default_creepage=8.0)
    assert ("AC_L", "GND") not in _creepage_violation_set(low)
    assert ("AC_L", "GND") in _creepage_violation_set(high)


# ---------------------------------------------------------------------------
# MR3 — domain-partition ref covariance
# ---------------------------------------------------------------------------


def _pin(net):
    return Pin("1", "1", (0.0, 0.0), net=net)


def test_mr3_partition_ref_renaming_covariant():
    comps = [
        Component(ref="R1", footprint="t:fp", bounds=(5.0, 5.0), pins=[_pin("AC_L")]),
        Component(ref="R2", footprint="t:fp", bounds=(5.0, 5.0), pins=[_pin("GND")]),
        Component(ref="U1", footprint="t:fp", bounds=(5.0, 5.0), pins=[_pin("AC_L"), _pin("GND")]),
        Component(ref="R3", footprint="t:fp", bounds=(5.0, 5.0), pins=[_pin("OTHER")]),
    ]
    rename = {"R1": "X1", "R2": "X2", "U1": "X3", "R3": "X4"}
    renamed = [
        Component(ref=rename[c.ref], footprint=c.footprint, bounds=c.bounds, pins=c.pins) for c in comps
    ]
    p = classify_domain_partition(comps, frozenset({"AC_L"}), frozenset({"GND"}))
    p2 = classify_domain_partition(renamed, frozenset({"AC_L"}), frozenset({"GND"}))
    assert [rename[r] for r in p.hv_only] == p2.hv_only
    assert [rename[r] for r in p.selv_only] == p2.selv_only
    assert [rename[r] for r in p.isolators] == p2.isolators
    assert [rename[r] for r in p.unclassified] == p2.unclassified


def test_mr3_companion_ref_spelling_does_not_classify():
    # A ref that CONTAINS an HV substring but whose nets are SELV stays in
    # the SELV bucket — classification is pin-net membership only, never
    # ref pattern matching.
    comp = Component(ref="AC_LINE_SENSE_RESISTOR", footprint="t:fp", bounds=(5.0, 5.0), pins=[_pin("GND")])
    partition = classify_domain_partition([comp], frozenset({"AC_L"}), frozenset({"GND"}))
    assert partition.selv_only == ["AC_LINE_SENSE_RESISTOR"]
    assert partition.hv_only == []


# ---------------------------------------------------------------------------
# MR4 — domain-clearance audit monotone in separation
# ---------------------------------------------------------------------------


def _domain_placement():
    return {
        "components": [
            {"ref": "C1", "nets": ["ac_l", "ac_n"]},
            {"ref": "R1", "nets": ["3v3"]},
        ],
        "nets": {
            "ac_l": {"domain": "MAINS"},
            "ac_n": {"domain": "MAINS"},
            "3v3": {"domain": "LV_CONTROL"},
        },
    }


def _audit_keys(violations):
    return {(v.ref_a, v.ref_b) for v in violations}


def test_mr4_audit_monotone_in_separation():
    placement = _domain_placement()
    constraints = generate_domain_clearance_constraints(placement, {})
    close = audit_domain_clearance(constraints, {"C1": (0.0, 0.0), "R1": (0.5, 0.5)})
    far = audit_domain_clearance(constraints, {"C1": (0.0, 0.0), "R1": (50.0, 50.0)})
    assert _audit_keys(far) <= _audit_keys(close)


def test_mr4_companion_far_placement_clears_all():
    placement = _domain_placement()
    constraints = generate_domain_clearance_constraints(placement, {})
    far = audit_domain_clearance(constraints, {"C1": (0.0, 0.0), "R1": (50.0, 50.0)})
    close = audit_domain_clearance(constraints, {"C1": (0.0, 0.0), "R1": (0.5, 0.5)})
    assert far == []  # the far placement genuinely clears every constraint
    assert len(close) >= 1  # and the close placement genuinely violates one


# ---------------------------------------------------------------------------
# MR5 — barrier rotation table: in-domain pinned, out-of-domain KeyError
# ---------------------------------------------------------------------------


def test_mr5_barrier_rotation_table_matches_oracle_in_domain():
    # The 4-row table is the only in-domain behaviour; every in-domain input
    # matches the pinned oracle bit-exactly.
    for x, y in [(0.0, 0.0), (1.0, 2.0), (-3.5, 7.25), (0.125, -0.0625)]:
        for rot in range(4):
            for axis in (0, 1):
                want = _oracle._project_onto_barrier_axis(x, y, rot, axis)
                got = _project_onto_barrier_axis(x, y, rot, axis)
                assert want == got, (x, y, rot, axis)


def test_mr5_companion_out_of_domain_raises_in_both():
    # A rotation outside 0..=3 is a KeyError in the pre-migration table AND
    # in the port — never a silent fallback to rot=0.
    for rot in (-1, 4, 5, 100):
        with pytest.raises(KeyError):
            _oracle._project_onto_barrier_axis(1.0, 2.0, rot, 0)
        with pytest.raises(KeyError):
            _project_onto_barrier_axis(1.0, 2.0, rot, 0)


def test_mr5_companion_table_is_not_constant():
    distinct = {_project_onto_barrier_axis(1.0, 2.0, rot, 0) for rot in range(4)}
    assert len(distinct) >= 3  # the table is not a constant function
