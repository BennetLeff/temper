"""Property-based tests for the Phase E batch E3 clearance-family
orchestration (temper-orchestration ``clearance`` module, exercised through
the delegation shims).

Rust Orchestration Engine plan 2026-08-09-001 Phase E E3. These properties
run against the production shims (``router_v6.{clearance_engine,
creepage_check, clearance_check}`` and ``placer.cp_sat.{isolation_barrier,
domain_clearance}``) and hold over randomized inputs.

Six non-vacuous properties (G4):

- P1  get_clearance absorbs the design-rule creepage: for ``design_rule_creepage
      > 0`` the result is at least that candidate (it is part of the
      conservative max). Vacuity guard: a kernel that drops the candidate
      violates (companion asserts the value rises with the candidate).
- P2  get_clearance internal-layer reduction: on every pair whose external
      result exceeds 0.5 mm the internal result is exactly 0.30 x external;
      otherwise the layer type does not change the result. Vacuity guard: a
      discriminator case with an HV pair is asserted to satisfy ``> 0.5``.
- P3  verify_creepage lazy contract: a board with no HV net reports zero
      checks and zero violations WITHOUT inspecting route geometry. Vacuity
      guard: the same input set with an HV net produces > 0 checks (the
      property is not vacuous on always-empty inputs).
- P4  verify_creepage violation monotonicity: increasing ``default_creepage``
      never decreases the violation count (the required distance is a
      threshold; relaxing it cannot add a pass). Vacuity guard: a case
      where the count actually rises with the threshold is asserted.
- P5  verify_clearance pair accounting: with n distinct nets, ``total_checks``
      is exactly C(n, 2) (every unordered pair is checked exactly once).
      Vacuity guard: an always-zero-total_checks kernel violates.
- P6  classify_domain_partition totals: every component lands in exactly one
      bucket (``total == len(components)``) and the four buckets are
      disjoint. Vacuity guard: a classifier that drops a component violates.
- P7  audit soundness: every audit violation either names a missing position
      (``actual_mm`` NaN) or has ``actual_mm < required_mm`` (the R24
      recomputed distance really is under the bound). Vacuity guard: a
      generated constraint set with a known under-margin pair is asserted
      to produce a violation.

Anti-vacuity per G4 is explicit in each property's ``_guard`` companion.
"""

from __future__ import annotations

import math

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from temper_placer.core.netlist import Component, Pin
from temper_placer.placer.cp_sat.domain_clearance import (
    audit_domain_clearance,
    generate_domain_clearance_constraints,
)
from temper_placer.placer.cp_sat.isolation_barrier import classify_domain_partition
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import verify_clearance
from temper_placer.router_v6.clearance_engine import get_clearance
from temper_placer.router_v6.creepage_check import verify_creepage
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults

_SETTINGS = settings(max_examples=120, deadline=4000, suppress_health_check=[])

_HV_NET = st.sampled_from(["AC_L", "AC_N", "HV_BUS", "MAINS_LIVE"])
_LV_NET = st.sampled_from(["SIG_A", "SIG_B", "GND_1", "VCC_3V3", "SPI_CLK"])
_NET_CLASS = st.sampled_from(["HV", "SIGNAL", "GND", "POWER", "MAINS", "AC_L", "+15V_LS"])
_VOLTAGE = st.one_of(
    st.just(0.0), st.just(5.0), st.just(230.0), st.just(340.0), st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
)
_LAYER_TYPE = st.sampled_from(["external", "internal"])


def _make_route(net_name, coords, layer="F.Cu", width_mm=0.127):
    length = math.hypot(coords[-1][0] - coords[0][0], coords[-1][1] - coords[0][1])
    return CompiledRoute(
        net_name=net_name,
        path=RoutePath(net_name=net_name, coordinates=list(coords), layer_name=layer, path_length=length),
        width_mm=width_mm,
        vias=[],
        matched_length_mm=None,
    )


@st.composite
def _route_results(draw):
    n = draw(st.integers(min_value=1, max_value=8))
    hv_fraction = draw(st.sampled_from([0.0, 0.1, 0.3, 1.0]))
    routes = {}
    ratings = {}
    for i in range(n):
        is_hv = draw(st.floats(min_value=0.0, max_value=1.0)) < hv_fraction
        base = draw(_HV_NET if is_hv else _LV_NET)
        net = f"{base}_{i}"
        if is_hv:
            ratings[net] = draw(st.floats(min_value=20.0, max_value=400.0, allow_nan=False, allow_infinity=False))
        x0 = draw(st.floats(min_value=0.0, max_value=40.0, allow_nan=False, allow_infinity=False))
        y0 = draw(st.floats(min_value=0.0, max_value=40.0, allow_nan=False, allow_infinity=False))
        x1 = draw(st.floats(min_value=0.0, max_value=40.0, allow_nan=False, allow_infinity=False))
        y1 = draw(st.floats(min_value=0.0, max_value=40.0, allow_nan=False, allow_infinity=False))
        routes[net] = _make_route(net, [(x0, y0), (x1, y1)])
    return RoutingResults(compiled_routes=routes, failed_nets=[]), ratings


# ---------------------------------------------------------------------------
# P1 — get_clearance absorbs the design-rule creepage candidate
# ---------------------------------------------------------------------------


@given(_NET_CLASS, _NET_CLASS, _VOLTAGE, _LAYER_TYPE)
@_SETTINGS
def test_p1_get_clearance_absorbs_design_rule_creepage(a, b, v, layer_type):
    drc = 6.5
    base = get_clearance(a, b, v, layer_type=layer_type)
    with_drc = get_clearance(a, b, v, layer_type=layer_type, design_rule_creepage=drc)
    # design_rule_creepage > 0 is a candidate, so the max includes it. On
    # external layers the candidate passes through unreduced; on internal
    # layers the IEC 60664-1 factor applies to the final max (the candidate
    # included), so the bound is drc * 0.30.
    factor = 0.30 if layer_type == "internal" else 1.0
    assert with_drc >= drc * factor
    assert with_drc >= base


def test_p1_guard_drc_candidate_is_discriminating():
    # The invariant discriminates a kernel that drops the candidate: a
    # non-HV pair whose natural result is far below 6.5mm must rise to 6.5
    # on an external layer.
    assert get_clearance("SIGNAL", "SIGNAL", 5.0, design_rule_creepage=6.5) == 6.5
    assert get_clearance("SIGNAL", "SIGNAL", 5.0) < 6.5


# ---------------------------------------------------------------------------
# P2 — get_clearance internal-layer reduction
# ---------------------------------------------------------------------------


@given(_NET_CLASS, _NET_CLASS, _VOLTAGE)
@_SETTINGS
def test_p2_internal_layer_reduction_is_exact_factor(a, b, v):
    ext = get_clearance(a, b, v, layer_type="external")
    internal = get_clearance(a, b, v, layer_type="internal")
    if ext > 0.5:
        assert internal == pytest.approx(ext * 0.30, rel=0, abs=0)
        assert internal < ext
    else:
        assert internal == ext


def test_p2_guard_factor_branch_is_reachable():
    ext = get_clearance("HV", "SIGNAL", 340.0, layer_type="external")
    internal = get_clearance("HV", "SIGNAL", 340.0, layer_type="internal")
    assert ext > 0.5  # the reduction branch is exercised, not vacuous
    assert internal == pytest.approx(ext * 0.30, rel=0, abs=0)


# ---------------------------------------------------------------------------
# P3 — verify_creepage lazy contract (no HV net -> zero checks)
# ---------------------------------------------------------------------------


@given(st.lists(_LV_NET, min_size=1, max_size=6))
@_SETTINGS
def test_p3_creepage_lazy_no_hv_net_zero_checks(nets):
    routes = {}
    for i, net in enumerate(nets):
        routes[f"{net}_{i}"] = _make_route(f"{net}_{i}", [(0.0, 0.0), (10.0, 10.0)])
    rr = RoutingResults(compiled_routes=routes, failed_nets=[])
    report = verify_creepage(rr)
    assert report.total_checks == 0
    assert report.violations == []


def test_p3_guard_laziness_discriminates():
    # The same shapes with an HV net present must produce checks — the
    # property is not vacuous on always-empty inputs.
    rr = RoutingResults(
        compiled_routes={
            "AC_L": _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)]),
            "GND": _make_route("GND", [(0.0, 0.2), (10.0, 0.2)]),
        },
        failed_nets=[],
    )
    report = verify_creepage(rr)
    assert report.total_checks > 0


# ---------------------------------------------------------------------------
# P4 — verify_creepage violation monotonicity in default_creepage
# ---------------------------------------------------------------------------


@given(_route_results())
@_SETTINGS
def test_p4_creepage_violation_count_monotone_in_threshold(data):
    rr, ratings = data
    low = verify_creepage(rr, ratings, default_creepage=1.0)
    high = verify_creepage(rr, ratings, default_creepage=8.0)
    # A larger required distance can only add violations, never remove them.
    assert len(low.violations) <= len(high.violations)
    assert low.total_checks == high.total_checks


def test_p4_guard_threshold_changes_count():
    rr = RoutingResults(
        compiled_routes={
            "AC_L": _make_route("AC_L", [(0.0, 0.0), (10.0, 0.0)]),
            "GND": _make_route("GND", [(0.0, 0.2), (10.0, 0.2)]),
        },
        failed_nets=[],
    )
    low = verify_creepage(rr, default_creepage=0.1)
    high = verify_creepage(rr, default_creepage=8.0)
    assert len(low.violations) < len(high.violations)  # the threshold moves the count


# ---------------------------------------------------------------------------
# P5 — verify_clearance pair accounting
# ---------------------------------------------------------------------------


@given(st.lists(st.sampled_from(["NET_A", "NET_B", "NET_C", "NET_D", "NET_E"]), min_size=2, max_size=7))
@_SETTINGS
def test_p5_clearance_pair_accounting_c_n_2(nets):
    uniq = sorted(set(nets))
    routes = {}
    for i, net in enumerate(uniq):
        routes[net] = _make_route(net, [(0.0, float(i)), (10.0, float(i))])
    rr = RoutingResults(compiled_routes=routes, failed_nets=[])
    report = verify_clearance(rr, backend="rust")
    n = len(uniq)
    assert report.total_checks == n * (n - 1) // 2


def test_p5_guard_pair_accounting_discriminates():
    # A kernel that skipped pairs would under-count; the oracle's C(3,2)=3
    # is asserted explicitly.
    rr = RoutingResults(
        compiled_routes={
            "NET_A": _make_route("NET_A", [(0.0, 0.0), (10.0, 0.0)]),
            "NET_B": _make_route("NET_B", [(0.0, 0.0), (10.0, 0.2)]),
            "NET_C": _make_route("NET_C", [(0.0, 0.0), (10.0, 0.4)]),
        },
        failed_nets=[],
    )
    report = verify_clearance(rr, backend="rust")
    assert report.total_checks == 3
    assert len(report.violations) > 0  # the close pairs really do violate


# ---------------------------------------------------------------------------
# P6 — classify_domain_partition totals
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.tuples(
            st.text(min_size=1, max_size=6),
            st.lists(st.sampled_from(["AC_L", "GND", "3V3", "OTHER"]), min_size=0, max_size=5),
        ),
        min_size=1,
        max_size=8,
    )
)
@_SETTINGS
def test_p6_partition_totals_and_disjointness(components):
    comps = [
        Component(ref=f"R{i}", footprint="t:fp", bounds=(5.0, 5.0), pins=[Pin("1", "1", (0.0, 0.0), net=n) for n in nets])
        for i, (_ref, nets) in enumerate(components)
    ]
    partition = classify_domain_partition(comps, frozenset({"AC_L"}), frozenset({"GND"}))
    assert partition.total == len(comps)
    assert (
        len(partition.hv_only + partition.selv_only + partition.isolators + partition.unclassified)
        == len(comps)
    )
    assert not (set(partition.hv_only) & set(partition.selv_only))


def test_p6_guard_partition_totals_discriminate():
    comps = [
        Component(ref="R1", footprint="t:fp", bounds=(5.0, 5.0), pins=[Pin("1", "1", (0.0, 0.0), net="AC_L")]),
        Component(ref="R2", footprint="t:fp", bounds=(5.0, 5.0), pins=[Pin("1", "1", (0.0, 0.0), net="GND")]),
        Component(ref="U1", footprint="t:fp", bounds=(5.0, 5.0), pins=[Pin("1", "1", (0.0, 0.0), net="AC_L"), Pin("2", "2", (5.0, 0.0), net="GND")]),
    ]
    partition = classify_domain_partition(comps, frozenset({"AC_L"}), frozenset({"GND"}))
    assert partition.hv_only == ["R1"]
    assert partition.selv_only == ["R2"]
    assert partition.isolators == ["U1"]
    assert partition.total == 3


# ---------------------------------------------------------------------------
# P7 — domain-clearance audit soundness
# ---------------------------------------------------------------------------


def _domain_placement(extra=()):
    components = [
        {"ref": "C1", "nets": ["ac_l", "ac_n"]},
        {"ref": "R1", "nets": ["3v3"]},
        {"ref": "R2", "nets": []},
    ]
    components.extend(extra)
    nets = {
        "ac_l": {"domain": "MAINS"},
        "ac_n": {"domain": "MAINS"},
        "3v3": {"domain": "LV_CONTROL"},
    }
    return {"components": components, "nets": nets}


@given(st.sampled_from([0.0, 0.5, 1.0, 2.0, 3.0]))
@_SETTINGS
def test_p7_audit_reports_only_real_or_missing(c1_dist):
    placement = _domain_placement()
    constraints = generate_domain_clearance_constraints(placement, {})
    positions = {"C1": (0.0, 0.0), "R1": (c1_dist, c1_dist)}
    violations = audit_domain_clearance(constraints, positions)
    for v in violations:
        if math.isnan(v.actual_mm):
            assert "missing resolved position" in v.reason
        else:
            assert v.actual_mm < v.required_mm


def test_p7_guard_audit_is_not_vacuous():
    # The far case must produce ZERO violations and the close case must
    # produce AT LEAST one — the property discriminates.
    placement = _domain_placement()
    constraints = generate_domain_clearance_constraints(placement, {})
    far = audit_domain_clearance(constraints, {"C1": (0.0, 0.0), "R1": (50.0, 50.0)})
    close = audit_domain_clearance(constraints, {"C1": (0.0, 0.0), "R1": (0.5, 0.5)})
    assert far == []
    assert len(close) >= 1
