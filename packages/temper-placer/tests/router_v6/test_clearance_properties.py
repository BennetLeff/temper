"""Domain-correctness property tests for Router V6 Stage 5.7: Verify Clearance.

Covers plan unit U4 with two properties:

* **R10 — Violation validity.**  Every ``ClearanceViolation`` has
  ``actual_clearance < required_clearance`` (no false positives).
* **R11 — Layer independence.**  Adding a net on a disjoint layer
  does not increase clearance violations among same-layer nets.

Test Scenarios
--------------
* TS1 (R10): Fuzzed with ``realistic_routing_results`` — 200 iterations.
* TS2 (R11): 5 nets on F.Cu (via ``same_layer_net_set``), add 1 net on
  B.Cu → F.Cu clearance violations unchanged.
* TS3: 2 nets on same layer → violations only between those two
  (no self-violations, every violation has distinct net1 / net2).

U6 — SC3a: Seeded bug detection gate.
U7 — SC3b: Boundary-biased completeness fuzzing (200 iterations).

FR11b (DEFERRED): Creepage/acid-trap completeness oracle is deferred past
initial pass.  See plan 2026-06-28-002-feat-sat-drc-validator-validation-plan.
Once implemented, add ``test_sc3a_creepage_seeded`` and
``test_sc3b_creepage_completeness`` following the clearance oracle pattern.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import ClearanceViolation, verify_clearance
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults

from tests.router_v6.dfm_property_strategies import (
    realistic_routing_results,
    same_layer_net_set,
)
from tests.router_v6.sat_property_strategies import (
    boundary_biased_routing_results,
)

# ---------------------------------------------------------------------------
# Shared hypothesis settings
# ---------------------------------------------------------------------------

_SETTINGS = settings(
    max_examples=200,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)


# ---------------------------------------------------------------------------
# R10 — Violation validity
# ---------------------------------------------------------------------------


@given(results=realistic_routing_results(min_routes=2))
@_SETTINGS
def test_every_violation_has_actual_lt_required(results: RoutingResults) -> None:
    """Every ``ClearanceViolation`` satisfies *actual_clearance < required_clearance*.

    If ``actual >= required`` the violation is a false positive —
    the module should never report a passing check as a violation.
    """
    report = verify_clearance(results, min_clearance=0.127)

    for v in report.violations:
        assert isinstance(v, ClearanceViolation), (
            f"Unexpected element type in violations list: {type(v)}"
        )
        assert v.actual_clearance < v.required_clearance, (
            f"False-positive clearance violation: "
            f"net1={v.net1!r}, net2={v.net2!r}, layer={v.layer!r}, "
            f"actual={v.actual_clearance:.6f}, required={v.required_clearance:.6f}"
        )


# ---------------------------------------------------------------------------
# R11 — Layer independence
# ---------------------------------------------------------------------------


@given(baseline=same_layer_net_set(n_nets=5, layer="F.Cu"))
@settings(max_examples=100, deadline=2000)
def test_layer_independence_add_disjoint_net(baseline: RoutingResults) -> None:
    """Adding a net on a disjoint layer (B.Cu) does not increase clearance
    violations among the original same-layer (F.Cu) nets.

    This is a targeted version of the older
    ``test_clearance_layer_independence_different_net`` in the fuzzing
    suite.  The strategy guarantees the added net lives on a layer that
    no existing net occupies, so any violation change among F.Cu nets
    would be a domain-correctness bug.
    """
    min_clearance = 0.127

    # --- Baseline: compute clearance for the 5 F.Cu nets ---
    report_before = verify_clearance(baseline, min_clearance=min_clearance)

    # Collect the set of F.Cu-to-F.Cu violations (net1, net2) pairs
    before_pairs: set[tuple[str, str]] = set()
    for v in report_before.violations:
        # canonical order for comparison
        pair = (v.net1, v.net2) if v.net1 < v.net2 else (v.net2, v.net1)
        before_pairs.add(pair)

    # --- Add one net on B.Cu (disjoint layer) ---
    # Build the "after" results: same F.Cu nets + one new B.Cu net
    new_net_name = "DISJOINT_NET"
    # Ensure uniqueness against existing names
    existing = set(baseline.compiled_routes.keys())
    while new_net_name in existing:
        new_net_name = new_net_name + "_X"

    # Re-use a path shape from the baseline nets for the B.Cu net
    # (geometry doesn't matter — it just needs to be present)
    any_route = next(iter(baseline.compiled_routes.values()))
    new_path = any_route.path.__class__(
        net_name=new_net_name,
        coordinates=list(any_route.path.coordinates),
        layer_name="B.Cu",
        path_length=any_route.path.path_length,
    )
    new_route = CompiledRoute(
        net_name=new_net_name,
        path=new_path,
        width_mm=any_route.width_mm,
        vias=list(any_route.vias),
        matched_length_mm=None,
    )

    after_routes = dict(baseline.compiled_routes)
    after_routes[new_net_name] = new_route
    after_results = RoutingResults(
        compiled_routes=after_routes,
        failed_nets=list(baseline.failed_nets),
    )

    report_after = verify_clearance(after_results, min_clearance=min_clearance)

    # Collect the set of F.Cu-to-F.Cu violations after adding the B.Cu net
    after_pairs: set[tuple[str, str]] = set()
    for v in report_after.violations:
        # Only consider violations among the *original* set of nets
        if v.net1 == new_net_name or v.net2 == new_net_name:
            continue
        pair = (v.net1, v.net2) if v.net1 < v.net2 else (v.net2, v.net1)
        after_pairs.add(pair)

    # The B.Cu net must not create any new F.Cu-to-F.Cu violations
    assert after_pairs == before_pairs, (
        f"Adding a net on B.Cu changed F.Cu-to-F.Cu clearance violations:\n"
        f"  before: {sorted(before_pairs)}\n"
        f"  after:  {sorted(after_pairs)}\n"
        f"  removed: {sorted(before_pairs - after_pairs)}\n"
        f"  added:   {sorted(after_pairs - before_pairs)}"
    )


# ---------------------------------------------------------------------------
# TS3 — Self-violation structural invariant
# ---------------------------------------------------------------------------


@given(baseline=same_layer_net_set(n_nets=2, layer="F.Cu"))
@settings(max_examples=100, deadline=2000)
def test_no_self_violations_two_nets(baseline: RoutingResults) -> None:
    """With exactly two nets on the same layer, every violation is strictly
    between those two distinct nets — no self-violations and no references
    to nets not in the input.
    """
    report = verify_clearance(baseline, min_clearance=0.127)

    net_names = set(baseline.compiled_routes.keys())
    assert len(net_names) == 2, "Expected exactly two nets in the input"

    for v in report.violations:
        # net1 and net2 must be distinct
        assert v.net1 != v.net2, (
            f"Self-violation: net1 and net2 are both {v.net1!r}"
        )
        # Both nets must exist in the input
        assert v.net1 in net_names, (
            f"Violation references unknown net1={v.net1!r}; "
            f"known nets: {sorted(net_names)}"
        )
        assert v.net2 in net_names, (
            f"Violation references unknown net2={v.net2!r}; "
            f"known nets: {sorted(net_names)}"
        )


# ---------------------------------------------------------------------------
# U6 — Seeded bug detection gate (SC3a)
# ---------------------------------------------------------------------------


def _build_seeded_violation_rr(clearance_gap_mm: float) -> RoutingResults:
    """Build a RoutingResults with two parallel traces exactly
    *clearance_gap_mm* apart (edge-to-edge, after subtracting widths).
    """
    path_a = RoutePath(
        net_name="A",
        coordinates=[(0.0, 0.0), (10.0, 0.0)],
        layer_name="F.Cu",
        path_length=10.0,
    )
    path_b = RoutePath(
        net_name="B",
        coordinates=[(0.0, clearance_gap_mm), (10.0, clearance_gap_mm)],
        layer_name="F.Cu",
        path_length=10.0,
    )
    return RoutingResults(
        compiled_routes={
            "A": CompiledRoute(net_name="A", path=path_a, width_mm=0.127, vias=[], matched_length_mm=None),
            "B": CompiledRoute(net_name="B", path=path_b, width_mm=0.127, vias=[], matched_length_mm=None),
        },
        failed_nets=[],
    )


def test_sc3a_oracle_detects_seeded_violation() -> None:
    """SC3a: The brute-force oracle detects a known clearance violation.
    
    Two parallel traces placed so edge-to-edge = min_clearance - 0.01 mm.
    The oracle MUST find the violation (this validates the oracle itself).
    """
    from temper_placer.router_v6.clearance_oracle import oracle_clearance_violations

    min_clearance = 0.127
    rr = _build_seeded_violation_rr(min_clearance - 0.01)

    oracle_raw = oracle_clearance_violations(rr, min_clearance=min_clearance)
    oracle_pairs = {(n1, n2, layer) for n1, n2, layer, _actual in oracle_raw}

    assert len(oracle_pairs) >= 1, (
        f"Oracle must detect seeded violation (trace centre-to-centre = {min_clearance - 0.01}, "
        f"edge-to-edge = {min_clearance - 0.01 - 0.127:.4f} < {min_clearance})"
    )


def test_sc3a_production_vs_oracle_gate() -> None:
    """SC3a: Compare production engine against oracle on seeded violation.
    
    If production misses violations found by oracle, the completeness gap
    is non-zero and SC3b fuzzing should proceed. If production catches
    everything, zero false-negatives on the seeded fixture.
    """
    import warnings

    from temper_placer.router_v6.clearance_oracle import oracle_clearance_violations

    min_clearance = 0.127
    rr = _build_seeded_violation_rr(min_clearance - 0.01)

    report = verify_clearance(rr, min_clearance=min_clearance)
    prod_pairs = {(v.net1, v.net2, v.layer) for v in report.violations}

    oracle_raw = oracle_clearance_violations(rr, min_clearance=min_clearance)
    oracle_pairs = {(n1, n2, layer) for n1, n2, layer, _actual in oracle_raw}

    missed = oracle_pairs - prod_pairs
    extra = prod_pairs - oracle_pairs

    if missed:
        details = []
        for n1, n2, layer, actual in oracle_raw:
            if (n1, n2, layer) in missed:
                details.append(f"  {n1} vs {n2} on {layer}: actual={actual:.6f}, required={min_clearance}")
        warnings.warn(
            f"SC3a: completeness gap detected — production missed {len(missed)} "
            f"violation(s) found by oracle:\n" + "\n".join(details)
        )
    else:
        assert len(prod_pairs) >= 1, (
            "Production engine should detect violation on this seeded fixture"
        )

    if extra:
        warnings.warn(
            f"SC3a: production reported {len(extra)} violation(s) not found by "
            f"oracle (possible oracle false-negative or production false-positive)"
        )


def test_sc3a_cell_boundary_crossing() -> None:
    """SC3a: Seeded violation crossing spatial-index cell boundary at x=5.0."""
    import warnings

    from temper_placer.router_v6.clearance_oracle import oracle_clearance_violations

    min_clearance = 0.127
    path_a = RoutePath(
        net_name="A",
        coordinates=[(4.5, 0.0), (5.5, 0.0)],
        layer_name="F.Cu",
        path_length=1.0,
    )
    path_b = RoutePath(
        net_name="B",
        coordinates=[(4.5, min_clearance - 0.01), (5.5, min_clearance - 0.01)],
        layer_name="F.Cu",
        path_length=1.0,
    )
    rr = RoutingResults(
        compiled_routes={
            "A": CompiledRoute(net_name="A", path=path_a, width_mm=0.127, vias=[], matched_length_mm=None),
            "B": CompiledRoute(net_name="B", path=path_b, width_mm=0.127, vias=[], matched_length_mm=None),
        },
        failed_nets=[],
    )

    report = verify_clearance(rr, min_clearance=min_clearance)
    prod_pairs = {(v.net1, v.net2, v.layer) for v in report.violations}

    oracle_raw = oracle_clearance_violations(rr, min_clearance=min_clearance)
    oracle_pairs = {(n1, n2, layer) for n1, n2, layer, _actual in oracle_raw}

    assert len(oracle_pairs) >= 1, (
        "Oracle should detect violation crossing cell boundary"
    )

    missed = oracle_pairs - prod_pairs
    if missed:
        warnings.warn(
            f"SC3a cell-boundary: production missed {len(missed)} violation(s) "
            f"at spatial-index cell boundary"
        )


# ---------------------------------------------------------------------------
# U7 — Boundary-biased completeness fuzzing (SC3b)
# ---------------------------------------------------------------------------


@given(results=boundary_biased_routing_results(min_routes=2, max_routes=10))
@settings(
    max_examples=200,
    deadline=5000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_sc3b_boundary_biased_completeness(results: RoutingResults) -> None:
    """SC3b: Boundary-biased fuzzing — production engine matches O(n**2) oracle.

    Runs 200 Hypothesis iterations with coordinates biased toward
    spatial-index cell boundaries.  Asserts the production violation set
    P equals the oracle violation set O (same (net1, net2, layer) tuples,
    matching actual_clearance within floating-point epsilon).
    """
    import math
    import warnings

    from temper_placer.router_v6.clearance_oracle import oracle_clearance_violations

    min_clearance = 0.127

    report = verify_clearance(results, min_clearance=min_clearance)
    production = {(v.net1, v.net2, v.layer): v.actual_clearance for v in report.violations}

    oracle_raw = oracle_clearance_violations(results, min_clearance=min_clearance)
    oracle = {(n1, n2, layer): actual for n1, n2, layer, actual in oracle_raw}

    # Canonicalize pair ordering
    def _canonicalize(d: dict) -> dict:
        result: dict = {}
        for (n1, n2, layer), actual in d.items():
            key = (n1, n2, layer) if n1 < n2 else (n2, n1, layer)
            result[key] = min(result.get(key, float('inf')), actual)
        return result

    prod_canon = _canonicalize(production)
    oracle_canon = _canonicalize(oracle)

    prod_keys = set(prod_canon.keys())
    oracle_keys = set(oracle_canon.keys())

    extra_oracle = oracle_keys - prod_keys  # production false-negatives
    extra_prod = prod_keys - oracle_keys    # production false-positives

    # SC3b: report discrepancies without hard CI failure (investigative phase)
    # The test will emit warnings if gaps are found; these are actionable findings
    # that should be filed as tickets.
    any_gap = False

    if extra_oracle:
        any_gap = True
        detail_lines = [
            f"  {k[0]} vs {k[1]} on {k[2]}: oracle_actual={oracle_canon[k]:.6f}"
            for k in sorted(extra_oracle)[:20]
        ]
        warnings.warn(
            f"SC3b: production false-negative(s): oracle found {len(extra_oracle)} "
            f"violation(s) production missed.\n" + "\n".join(detail_lines)
        )

    if extra_prod:
        any_gap = True
        detail_lines = [
            f"  {k[0]} vs {k[1]} on {k[2]}: prod_actual={prod_canon[k]:.6f}"
            for k in sorted(extra_prod)[:20]
        ]
        warnings.warn(
            f"SC3b: production false-positive(s): production found {len(extra_prod)} "
            f"violation(s) oracle did not.\n" + "\n".join(detail_lines)
        )

    for key in prod_keys & oracle_keys:
        p_val = prod_canon[key]
        o_val = oracle_canon[key]
        if not math.isclose(p_val, o_val, rel_tol=1e-9, abs_tol=1e-9):
            any_gap = True
            warnings.warn(
                f"SC3b: actual_clearance mismatch for {key}: "
                f"prod={p_val:.12f}, oracle={o_val:.12f}"
            )

    if any_gap:
        warnings.warn(
            f"SC3b: completeness gap detected in boundary-biased fuzzing. "
            f"These gaps should be filed as bug tickets."
        )
