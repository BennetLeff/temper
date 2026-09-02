"""R1a: behavioural A/B of the Phase E batch E3 clearance-family Rust
orchestration (temper-orchestration ``clearance`` module) against the pinned
pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase E E3: the five
clearance-family modules' ORCHESTRATION moves to temper-orchestration's
``clearance.rs`` (Stage<BoardState> impls + the pyfunction FFI surface);
the modules keep their public API as delegation shims. The pre-migration
implementation is pinned VERBATIM as ``tests/router_v6/_clearance_family_py_oracle.py``
(byte-identical snapshot at the dispatch base; content-hash pinned in
``scripts/oracle_hashes.json`` AND in this file's body digest). Both arms
are driven with IDENTICAL inputs; every assertion is bit-exact (floats via
``float.hex()`` via ``canon``, list/field identity via the per-check
comparators below).

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` asserts
each shim function now binds to a ``temper_orchestration`` pyfunction
(``__module__`` / import binding), not resolving back onto the oracle.

Covered orchestrations:

- ``clearance_engine.get_clearance``        vs ``clearance::get_clearance_py``
- ``creepage_check.verify_creepage``        vs ``clearance::run_creepage_check``
  - ``clearance_check.verify_clearance``      vs ``clearance::run_clearance_check``
  (the production Rust path vs the immutable pre-migration oracle)
- ``isolation_barrier.{classify_domain_partition, evaluate_isolator_feasibility,
  _project_onto_barrier_axis}``              vs ``clearance::*_py``
- ``domain_clearance.{generate_domain_clearance_constraints,
  generate_unclassified_hv_keepaway_constraints,
  find_intra_footprint_domain_conflicts, audit_domain_clearance}``
                                             vs ``clearance::*_py``
"""

from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.placer.cp_sat.domain_clearance import (
    audit_domain_clearance as shim_audit,
)
from temper_placer.placer.cp_sat.domain_clearance import (
    find_intra_footprint_domain_conflicts as shim_conflicts,
)
from temper_placer.placer.cp_sat.domain_clearance import (
    generate_domain_clearance_constraints as shim_generate,
)
from temper_placer.placer.cp_sat.domain_clearance import (
    generate_unclassified_hv_keepaway_constraints as shim_keepaway,
)
from temper_placer.placer.cp_sat.isolation_barrier import (
    IsolatorPadGroups,
    Pad,
)
from temper_placer.placer.cp_sat.isolation_barrier import (
    _project_onto_barrier_axis as shim_project,
)
from temper_placer.placer.cp_sat.isolation_barrier import (
    classify_domain_partition as shim_partition,
)
from temper_placer.placer.cp_sat.isolation_barrier import (
    evaluate_isolator_feasibility as shim_feasibility,
)
from temper_placer.requirements.validators.clearance import IEC60335_REQUIREMENTS
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import verify_clearance
from temper_placer.router_v6.clearance_engine import get_clearance
from temper_placer.router_v6.creepage_check import verify_creepage
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from tests.core._contract_canon import canon
from tests.router_v6 import _clearance_family_py_oracle as _oracle

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_clearance_family_py_oracle.py")


def test_oracle_body_matches_pinned_digest() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied bodies are content-addressed. If this fails,
    either the oracle was edited (revert it) or a pre-migration module's
    source really changed upstream (re-pin deliberately, in its own commit).
    """
    text = _ORACLE_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    # Re-pinned 2026-08-14 (its own commit): the pre-migration
    # `get_clearance` body's material_group discard and un-floored
    # internal-layer reduction were confirmed defects (not intended
    # reference behavior) and corrected here to match the now-fixed Rust
    # side -- see the oracle module's own docstring "RE-PIN" section for
    # the exhaustive-sweep evidence this was gated on.
    assert digest == "03508551f7a70d58d0fcf8fd59772d1f4643408058d176bbd04bdbfc10abe145", (
        "the pinned oracle file changed; it must stay verbatim "
        "(see scripts/oracle_hashes.json for the registered hash)"
    )


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the shims must bind to temper_orchestration pyfunctions,
    not resolve back onto the oracle."""
    import temper_orchestration as _to

    assert _to.get_clearance_py.__module__ == "temper_orchestration.temper_orchestration"
    assert _to.run_creepage_check.__module__ == "temper_orchestration.temper_orchestration"
    assert _to.run_clearance_check.__module__ == "temper_orchestration.temper_orchestration"
    assert _to.classify_domain_partition_py.__module__ == "temper_orchestration.temper_orchestration"
    assert (
        _to.evaluate_isolator_feasibility_py.__module__
        == "temper_orchestration.temper_orchestration"
    )
    assert (
        _to.domain_clearance_constraints_py.__module__
        == "temper_orchestration.temper_orchestration"
    )
    # The shim functions are live delegations (bound at import), the oracle
    # functions are the verbatim pre-migration bodies.
    assert get_clearance.__module__ == "temper_placer.router_v6.clearance_engine"
    assert _oracle.get_clearance is not get_clearance


# ---------------------------------------------------------------------------
# clearance_engine.get_clearance
# ---------------------------------------------------------------------------


def _canon_float(f: float) -> str:
    return canon(f)


NET_CLASSES = ["HV", "SIGNAL", "GND", "POWER", "MAINS", "AC_L", "+15V_LS", "DC_BUS_RTN", "LV"]
VOLTAGES = [0.0, 5.0, 12.0, 48.0, 230.0, 340.0, 500.0, 1000.0]


@pytest.mark.parametrize("seed", range(25))
def test_get_clearance_matches_oracle_bit_exact(seed):
    rng = random.Random(seed * 31 + 5)
    for _ in range(40):
        a = rng.choice(NET_CLASSES)
        b = rng.choice(NET_CLASSES)
        v = rng.choice(VOLTAGES)
        layer_type = rng.choice(["external", "internal"])
        pd = rng.choice([1, 2, 3])
        drc = rng.choice([None, 0.0, 1.0, 6.5])
        want = _oracle.get_clearance(a, b, v, layer_type=layer_type, pollution_degree=pd)
        if drc is None:
            got = get_clearance(a, b, v, layer_type=layer_type, pollution_degree=pd)
        else:
            got = get_clearance(
                a, b, v, layer_type=layer_type, pollution_degree=pd, design_rule_creepage=drc
            )
            want = _oracle.get_clearance(
                a, b, v, layer_type=layer_type, pollution_degree=pd, design_rule_creepage=drc
            )
        assert _canon_float(want) == _canon_float(got), (
            f"seed={seed} ({a},{b},{v},{layer_type},{pd}): oracle={want!r} rust={got!r}"
        )


def test_get_clearance_nan_voltage_matches_oracle():
    for layer_type in ("external", "internal"):
        want = _oracle.get_clearance("HV", "SIGNAL", float("nan"), layer_type=layer_type)
        got = get_clearance("HV", "SIGNAL", float("nan"), layer_type=layer_type)
        assert _canon_float(want) == _canon_float(got)


# ---------------------------------------------------------------------------
# creepage_check.verify_creepage
# ---------------------------------------------------------------------------


def _make_route(net_name, coords, layer="F.Cu", width_mm=0.127, vias=None):
    length = 0.0
    for i in range(len(coords) - 1):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        length += math.hypot(dx, dy)
    return CompiledRoute(
        net_name=net_name,
        path=RoutePath(
            net_name=net_name, coordinates=list(coords), layer_name=layer, path_length=length
        ),
        width_mm=width_mm,
        vias=list(vias) if vias else [],
        matched_length_mm=None,
    )


def _random_creepage_routes(rng, n_routes, hv_fraction):
    hv_bases = ["AC_L", "AC_N", "HV_BUS", "MAINS_LIVE"]
    lv_bases = ["SIG_A", "SIG_B", "GND_1", "VCC_3V3"]
    routes = {}
    voltage_ratings = {}
    for i in range(n_routes):
        is_hv = rng.random() < hv_fraction
        base = rng.choice(hv_bases if is_hv else lv_bases)
        net = f"{base}_{i}"
        if is_hv:
            voltage_ratings[net] = rng.uniform(20.0, 400.0)
        x, y = rng.uniform(0, 40), rng.uniform(0, 40)
        coords = [(x, y)]
        for _ in range(rng.randint(1, 4)):
            coords.append((min(40.0, max(0.0, x + rng.uniform(-6, 6))), min(40.0, max(0.0, y + rng.uniform(-6, 6)))))
        routes[net] = _make_route(net, coords)
    return routes, voltage_ratings


def _canon_creepage_violation(v):
    return (
        v.hv_net,
        v.lv_net,
        canon(v.location[0]),
        canon(v.location[1]),
        canon(v.actual_distance),
        canon(v.required_distance),
    )


def _assert_creepage_same(rr, voltage_ratings=None, default_creepage=None, msg=""):
    want = _oracle.verify_creepage(rr, voltage_ratings, default_creepage)
    got = verify_creepage(rr, voltage_ratings, default_creepage)
    assert want.total_checks == got.total_checks, f"{msg}: total_checks"
    assert [v.deficiency for v in want.violations] == [v.deficiency for v in got.violations]
    assert [_canon_creepage_violation(v) for v in want.violations] == [
        _canon_creepage_violation(v) for v in got.violations
    ], f"{msg}: violations differ"


def test_verify_creepage_empty():
    rr = RoutingResults(compiled_routes={}, failed_nets=[])
    _assert_creepage_same(rr, msg="empty")


def test_verify_creepage_no_hv_nets():
    rr = RoutingResults(
        compiled_routes={"SIG1": _make_route("SIG1", [(0, 0), (10, 10)])}, failed_nets=[]
    )
    _assert_creepage_same(rr, msg="no_hv")


def test_verify_creepage_hv_pair():
    rr = RoutingResults(
        compiled_routes={
            "AC_L": _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)]),
            "GND": _make_route("GND", [(0.0, 0.2), (10.0, 0.2)]),
        },
        failed_nets=[],
    )
    _assert_creepage_same(rr, msg="hv_pair")


@pytest.mark.parametrize("seed", range(15))
def test_verify_creepage_random(seed):
    rng = random.Random(seed * 17 + 3)
    routes, ratings = _random_creepage_routes(rng, rng.randint(2, 12), rng.choice([0.0, 0.1, 0.3]))
    rr = RoutingResults(compiled_routes=routes, failed_nets=[])
    default = rng.choice([None, 4.0, 8.0])
    _assert_creepage_same(rr, ratings, default, msg=f"seed={seed}")


def test_verify_creepage_default_creepage_override():
    rr = RoutingResults(
        compiled_routes={
            "AC_L": _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)]),
            "SIG1": _make_route("SIG1", [(0.0, 1.0), (10.0, 1.0)]),
        },
        failed_nets=[],
    )
    _assert_creepage_same(rr, None, 4.0, msg="default_creepage")


# ---------------------------------------------------------------------------
# clearance_check.verify_clearance — production rust path vs pinned oracle
# ---------------------------------------------------------------------------

LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]


def _canon_clearance_violation(v):
    return (
        frozenset({v.net1, v.net2}),
        v.layer,
        canon(v.actual_clearance),
        canon(v.required_clearance),
    )


def _assert_clearance_same(rr, min_clearance=0.127, voltage_ratings=None, msg=""):
    want = _oracle._verify_clearance_python(rr, min_clearance, voltage_ratings)
    got = verify_clearance(rr, min_clearance=min_clearance, voltage_ratings=voltage_ratings, backend="rust")
    assert want.total_checks == got.total_checks, f"{msg}: total_checks"
    assert sorted(_canon_clearance_violation(v) for v in want.violations) == sorted(
        _canon_clearance_violation(v) for v in got.violations
    ), f"{msg}: violation sets differ"


def test_clearance_check_empty():
    rr = RoutingResults(compiled_routes={}, failed_nets=[])
    _assert_clearance_same(rr, msg="empty")


def test_clearance_check_overlapping():
    rr = RoutingResults(
        compiled_routes={
            "NET1": _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width_mm=0.5),
            "NET2": _make_route("NET2", [(0.0, 0.1), (10.0, 0.1)], width_mm=0.5),
        },
        failed_nets=[],
    )
    _assert_clearance_same(rr, msg="overlapping")


def test_clearance_check_hv_voltage_ratings():
    rr = RoutingResults(
        compiled_routes={
            "HV_BUS": _make_route("HV_BUS", [(0.0, 0.0), (10.0, 0.0)]),
            "AC_L": _make_route("AC_L", [(0.0, 0.5), (10.0, 0.5)]),
        },
        failed_nets=[],
    )
    _assert_clearance_same(rr, voltage_ratings={"HV_BUS": 100.0, "AC_L": 400.0}, msg="hv")


@pytest.mark.parametrize("seed", range(10))
def test_clearance_check_random(seed):
    rng = random.Random(seed * 41 + 9)
    routes, ratings = _random_creepage_routes(rng, rng.randint(2, 10), rng.choice([0.0, 0.1, 0.3]))
    rr = RoutingResults(compiled_routes=routes, failed_nets=[])
    mc = rng.choice([0.127, 0.5, 2.0])
    _assert_clearance_same(rr, mc, ratings, msg=f"seed={seed}")


# ---------------------------------------------------------------------------
# isolation_barrier — partition, feasibility, rotation projection
# ---------------------------------------------------------------------------

HV = frozenset({"AC_L", "AC_N", "DC_BUS"})
SELV = frozenset({"GND", "+3V3"})


def _comp(ref, pins):
    return Component(ref=ref, footprint="test:fp", bounds=(5.0, 5.0), pins=pins)


def _circle_pad(x, y, radius):
    return Pad(x=x, y=y, width=2 * radius, height=2 * radius, shape="circle")


def test_classify_domain_partition_matches_oracle():
    comps = [
        _comp("R1", [Pin("1", "1", (0, 0), net="AC_L")]),
        _comp("R2", [Pin("1", "1", (0, 0), net="GND")]),
        _comp(
            "U1",
            [Pin("1", "1", (0, 0), net="AC_L"), Pin("2", "2", (5, 0), net="GND")],
        ),
        _comp("R3", [Pin("1", "1", (0, 0), net="SOME_OTHER_NET")]),
        _comp("R9", [Pin("1", "1", (0, 0), net="AC_LINE_SENSE")]),
    ]
    want = _oracle.classify_domain_partition(comps, HV, SELV)
    got = shim_partition(comps, HV, SELV)
    assert (want.hv_only, want.selv_only, want.isolators, want.unclassified) == (
        got.hv_only,
        got.selv_only,
        got.isolators,
        got.unclassified,
    )
    assert want.total == got.total


def test_project_onto_barrier_axis_matches_oracle():
    for rot in range(4):
        for axis in (0, 1):
            for x, y in [(0.0, 0.0), (1.0, 2.0), (-3.5, 7.25)]:
                want = _oracle._project_onto_barrier_axis(x, y, rot, axis)
                got = shim_project(x, y, rot, axis)
                assert canon(want) == canon(got), (x, y, rot, axis)


def _groups_for(ref, hv_pads, selv_pads):
    return IsolatorPadGroups(ref=ref, hv_pads=hv_pads, selv_pads=selv_pads, other_pads=[])


def test_evaluate_isolator_feasibility_matches_oracle_feasible():
    groups = _groups_for(
        "PS1",
        [_circle_pad(0.0, 0.0, 1.5), _circle_pad(0.0, 10.75, 1.5)],
        [_circle_pad(38.5, 10.75, 1.5), _circle_pad(38.5, 2.75, 1.5)],
    )
    for barrier_axis in (0, 1):
        want = _oracle.evaluate_isolator_feasibility(groups, 8.5, barrier_axis)
        got = shim_feasibility(groups, 8.5, barrier_axis)
        assert want.feasible == got.feasible
        assert (canon(want.gap_x_mm), canon(want.gap_y_mm), canon(want.achievable_gap_mm)) == (
            canon(got.gap_x_mm),
            canon(got.gap_y_mm),
            canon(got.achievable_gap_mm),
        )
        assert (want.chosen_rotation, want.feasible_axis, want.hv_is_lo) == (
            got.chosen_rotation,
            got.feasible_axis,
            got.hv_is_lo,
        )


def test_evaluate_isolator_feasibility_matches_oracle_rotation_search():
    # K1-shaped isolator: HV/SELV clusters overlap on X, separate on Y — the
    # 90-degree rotation path (barrier_axis=0 must still be feasible).
    groups = _groups_for(
        "K1",
        [_circle_pad(-3.175, 9.5, 3.17), _circle_pad(3.175, 9.5, 3.17)],
        [_circle_pad(-3.175, 0.0, 0.9), _circle_pad(3.175, 0.0, 0.9)],
    )
    for width in (4.0, 8.5):
        want = _oracle.evaluate_isolator_feasibility(groups, width, barrier_axis=0)
        got = shim_feasibility(groups, width, barrier_axis=0)
        assert want.feasible == got.feasible, width
        assert (want.chosen_rotation, want.feasible_axis, want.hv_is_lo) == (
            got.chosen_rotation,
            got.feasible_axis,
            got.hv_is_lo,
        )
        assert canon(want.achievable_gap_mm) == canon(got.achievable_gap_mm)


def test_evaluate_isolator_feasibility_non_isolator_error_matches():
    groups = IsolatorPadGroups(ref="R1", hv_pads=[], selv_pads=[], other_pads=[])
    with pytest.raises(ValueError, match="R1: not a real isolator"):
        _oracle.evaluate_isolator_feasibility(groups, 8.5)
    with pytest.raises(ValueError, match="R1: not a real isolator"):
        shim_feasibility(groups, 8.5)


# ---------------------------------------------------------------------------
# domain_clearance — generator, keep-away, intra-footprint, audit
# ---------------------------------------------------------------------------


def _domain_placement(extra=()):
    components = [
        {"ref": "C1", "nets": ["ac_l", "ac_n"]},
        {"ref": "R1", "nets": ["3v3"]},
        {"ref": "R2", "nets": []},
    ]
    for item in extra:
        components.append(item)
    nets = {
        "ac_l": {"domain": "MAINS"},
        "ac_n": {"domain": "MAINS"},
        "3v3": {"domain": "LV_CONTROL"},
    }
    return {"components": components, "nets": nets}


def _matrix_rows():
    return [
        (
            da.value,
            db.value,
            ins.value,
            req["min_clearance_mm"],
            req["min_creepage_mm"],
            req["design_value_mm"],
        )
        for (da, db, ins), req in IEC60335_REQUIREMENTS.items()
    ]


def _canon_constraint(c):
    return (c.a, c.b, canon(c.min_distance_mm), c.tier, c.because, c.id)


def test_generate_domain_clearance_constraints_matches_oracle():
    placement = _domain_placement()
    want = _oracle.generate_domain_clearance_constraints(placement, {})
    got = shim_generate(placement, {})
    assert [_canon_constraint(c) for c in want] == [_canon_constraint(c) for c in got]
    assert [c.id for c in want] == [c.id for c in got]


def test_generate_domain_clearance_constraints_component_refs_filter():
    placement = _domain_placement()
    for refs in (None, {"C1", "R1"}, {"C1"}, set()):
        want = _oracle.generate_domain_clearance_constraints(placement, {}, refs)
        got = shim_generate(placement, {}, refs)
        assert [_canon_constraint(c) for c in want] == [_canon_constraint(c) for c in got]


def test_keepaway_constraints_matches_oracle():
    placement = _domain_placement()
    for refs in ({"C1", "R1", "R2"}, {"C1", "R2"}, {"R2"}):
        want = _oracle.generate_unclassified_hv_keepaway_constraints(placement, {}, refs)
        got = shim_keepaway(placement, {}, refs)
        assert [_canon_constraint(c) for c in want] == [_canon_constraint(c) for c in got]


def test_keepaway_constraints_exempt_pairs_matches_oracle():
    placement = _domain_placement()
    exempt = {frozenset({"R2", "C1"})}
    want = _oracle.generate_unclassified_hv_keepaway_constraints(placement, {}, {"C1", "R1", "R2"}, exempt)
    got = shim_keepaway(placement, {}, {"C1", "R1", "R2"}, exempt)
    assert [_canon_constraint(c) for c in want] == [_canon_constraint(c) for c in got]


def _canon_conflict(c):
    return (c.ref, c.domain_a.value, c.domain_b.value, canon(c.margin_mm), c.reason)


def test_find_intra_footprint_domain_conflicts_matches_oracle():
    # C6 straddles MAINS and LV_CONTROL (the DC_BUS<->LV_CONTROL rows).
    placement = _domain_placement(
        extra=[{"ref": "C6", "nets": ["ac_l", "3v3"]}, {"ref": "C7", "nets": ["ac_l", "ac_n"]}]
    )
    for refs in (None, {"C1", "C6", "R1"}, {"C6"}):
        want = _oracle.find_intra_footprint_domain_conflicts(placement, {}, refs)
        got = shim_conflicts(placement, {}, refs)
        assert [_canon_conflict(c) for c in want] == [_canon_conflict(c) for c in got]


def test_audit_domain_clearance_matches_oracle():
    placement = _domain_placement()
    constraints = shim_generate(placement, {})
    positions = {"C1": (0.0, 0.0), "R1": (1.0, 1.0)}
    want = _oracle.audit_domain_clearance(constraints, positions)
    got = shim_audit(constraints, positions)
    assert [_canon_audit(v) for v in want] == [_canon_audit(v) for v in got]


def test_audit_domain_clearance_missing_position_matches_oracle():
    placement = _domain_placement()
    constraints = shim_generate(placement, {})
    want = _oracle.audit_domain_clearance(constraints, {"C1": (0.0, 0.0)})
    got = shim_audit(constraints, {"C1": (0.0, 0.0)})
    assert [_canon_audit(v) for v in want] == [_canon_audit(v) for v in got]


def _canon_audit(v):
    # NaN actual_mm compares equal to NaN.
    actual = "nan" if math.isnan(v.actual_mm) else canon(v.actual_mm)
    return (v.ref_a, v.ref_b, canon(v.required_mm), actual, v.reason)
