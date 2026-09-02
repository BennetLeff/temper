"""
Tests for Router V6 Stage 5.7: Verify Clearance

Part of temper-8vjm
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    ClearanceViolation,
    _is_hv_keyword_match,
    verify_clearance,
)
from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.routing_results import (
    CompiledRoute,
    CompiledTreeRoute,
    RoutingResults,
)
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry


def test_verify_no_routes():
    """Test clearance verification with no routes."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])

    report = verify_clearance(results)

    assert report.violation_count == 0
    assert report.total_checks == 0


@pytest.mark.parametrize(
    ("backend", "has_rust_clearance", "has_orchestration"),
    [
        ("auto", False, True),
        ("auto", True, False),
        ("rust", False, True),
        ("rust", True, False),
    ],
)
def test_verify_clearance_fails_closed_without_complete_rust_backend(
    monkeypatch, backend, has_rust_clearance, has_orchestration
):
    """A missing Rust half must never silently re-enable Python clearance."""
    import temper_placer.router_v6.clearance_check as clearance_module

    monkeypatch.setattr(clearance_module, "_HAS_RUST_CLEARANCE", has_rust_clearance)
    monkeypatch.setattr(clearance_module, "_HAS_RUN_CLEARANCE_CHECK", has_orchestration)

    with pytest.raises(RuntimeError, match="Rust clearance engine is required"):
        verify_clearance(RoutingResults(compiled_routes={}, failed_nets=[]), backend=backend)


@pytest.mark.parametrize(
    ("has_rust_clearance", "has_orchestration"),
    [(False, True), (True, False)],
)
def test_verify_clearance_default_fails_closed_without_complete_rust_backend(
    monkeypatch, has_rust_clearance, has_orchestration
):
    """The default selector has the same fail-closed contract as ``auto``."""
    import temper_placer.router_v6.clearance_check as clearance_module

    monkeypatch.setattr(clearance_module, "_HAS_RUST_CLEARANCE", has_rust_clearance)
    monkeypatch.setattr(clearance_module, "_HAS_RUN_CLEARANCE_CHECK", has_orchestration)

    with pytest.raises(RuntimeError, match="Rust clearance engine is required"):
        verify_clearance(RoutingResults(compiled_routes={}, failed_nets=[]))


def test_verify_clearance_python_backend_is_retired(monkeypatch):
    """The compatibility selector cannot re-enable the deleted Python path."""
    import temper_placer.router_v6.clearance_check as clearance_module

    monkeypatch.setattr(clearance_module, "_HAS_RUST_CLEARANCE", True)
    monkeypatch.setattr(clearance_module, "_HAS_RUN_CLEARANCE_CHECK", True)

    with pytest.raises(RuntimeError, match="backend='python' was retired"):
        verify_clearance(RoutingResults(compiled_routes={}, failed_nets=[]), backend="python")


def test_verify_single_route():
    """Test clearance with single route (no violations possible)."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])

    report = verify_clearance(results)

    assert report.violation_count == 0


def test_verify_safe_clearance():
    """Test routes with safe clearance."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    route1 = CompiledRoute("NET1", path1, 0.127, [], None)

    path2 = RoutePath("NET2", [(0, 5), (10, 5)], "F.Cu", 10.0)
    route2 = CompiledRoute("NET2", path2, 0.127, [], None)

    results = RoutingResults(compiled_routes={"NET1": route1, "NET2": route2}, failed_nets=[])

    report = verify_clearance(results, min_clearance=0.127)

    # 5mm spacing >> 0.127mm requirement
    assert report.violation_count == 0


def test_verify_clearance_violation():
    """Test routes with insufficient clearance."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    route1 = CompiledRoute("NET1", path1, 0.2, [], None)  # Wide trace

    path2 = RoutePath("NET2", [(0, 0.2), (10, 0.2)], "F.Cu", 10.0)
    route2 = CompiledRoute("NET2", path2, 0.2, [], None)  # Wide trace

    results = RoutingResults(compiled_routes={"NET1": route1, "NET2": route2}, failed_nets=[])

    report = verify_clearance(results, min_clearance=0.127)

    # Edge-to-edge: 0.2 - 0.1 - 0.1 = 0.0 < 0.127mm
    assert report.violation_count > 0


def test_clearance_violation_dataclass():
    """Test ClearanceViolation dataclass."""
    violation = ClearanceViolation(
        net1="NET1",
        net2="NET2",
        location=(5.0, 5.0),
        actual_clearance=0.05,
        required_clearance=0.127,
        layer="F.Cu",
    )

    assert violation.net1 == "NET1"
    assert violation.net2 == "NET2"
    assert violation.layer == "F.Cu"
    assert violation.deficiency == pytest.approx(0.077)


def test_clearance_report_dataclass():
    """Test ClearanceReport dataclass."""
    violation = ClearanceViolation("NET1", "NET2", (0, 0), 0.05, 0.127, "F.Cu")

    report = ClearanceReport(violations=[violation], total_checks=10)

    assert report.violation_count == 1
    assert report.total_checks == 10
    assert report.pass_rate == 90.0


def test_hv_clearance_requirement():
    """Test increased clearance for HV nets."""
    # HV net
    hv_path = RoutePath("AC_L", [(0, 0), (10, 0)], "F.Cu", 10.0)
    hv_route = CompiledRoute("AC_L", hv_path, 0.127, [], None)

    # Regular net
    sig_path = RoutePath("SIG1", [(0, 0.4), (10, 0.4)], "F.Cu", 10.0)
    sig_route = CompiledRoute("SIG1", sig_path, 0.127, [], None)

    results = RoutingResults(compiled_routes={"AC_L": hv_route, "SIG1": sig_route}, failed_nets=[])

    # Standard clearance 0.127mm
    report = verify_clearance(results, min_clearance=0.127)

    # Should still violate due to HV requiring 0.5mm
    # Edge-to-edge: ~0.336mm < 0.5mm
    assert report.violation_count > 0


def test_multiple_route_pairs():
    """Test clearance checking multiple route combinations."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    route1 = CompiledRoute("NET1", path1, 0.127, [], None)

    path2 = RoutePath("NET2", [(0, 5), (10, 5)], "F.Cu", 10.0)
    route2 = CompiledRoute("NET2", path2, 0.127, [], None)

    path3 = RoutePath("NET3", [(0, 10), (10, 10)], "F.Cu", 10.0)
    route3 = CompiledRoute("NET3", path3, 0.127, [], None)

    results = RoutingResults(
        compiled_routes={
            "NET1": route1,
            "NET2": route2,
            "NET3": route3,
        },
        failed_nets=[],
    )

    report = verify_clearance(results)

    # Should check 3 pairs: NET1-NET2, NET1-NET3, NET2-NET3
    assert report.total_checks == 3


def _make_tree_route(net_name: str, other_x: float, y: float) -> CompiledTreeRoute:
    root = PadIdentity("U1", "1", net_name, 0.0, y, (0,))
    leaf = PadIdentity("U2", "1", net_name, other_x, y, (0,))
    geometry = TreeRouteGeometry(
        net_name,
        (
            TreeRouteBranch(
                TerminalTreeEdge(root, leaf),
                RoutePath(net_name, [(0, y), (other_x, y)], "F.Cu", abs(other_x)),
            ),
        ),
    )
    return CompiledTreeRoute(net_name=net_name, geometry=geometry, width_mm=0.2, vias=[])


@pytest.mark.parametrize("backend", ["rust", "auto"])
def test_verify_clearance_inspects_tree_routed_nets(backend):
    """Regression: tree-routed nets were invisible to clearance checking.

    ``verify_clearance`` used to walk only ``routing_results.compiled_routes``.
    ``RoutingResults.tree_routes`` / ``.partial_tree_routes`` hold
    ``CompiledTreeRoute`` objects (Steiner/multi-terminal routes) with their
    own copper geometry (``.geometry``) -- these were never checked against
    anything, so two tree-routed nets could overlap with zero clearance and
    the check would report 0 checks / 0 violations for that pair. Same class
    of bug as the ``annular_ring`` tree-route gap fixed in
    docs/evidence/2026-07-27-drc-checks-repaired.md. See
    docs/evidence/2026-07-27-clearance-copper-balance.md.

    Fails before the fix (``total_checks == 0``, tree routes never entered
    the pairwise walk at all); passes after (``total_checks == 1`` and the
    overlapping tree-routed pair is caught).
    """
    # Two tree-routed nets, both running along y=0 and y=0.05mm for 10mm --
    # 0.05mm apart, well under any plausible clearance requirement, exactly
    # like test_creepage_violation_count_bounded_by_net_pair_not_segment_pair's
    # fixture shape.
    tree1 = _make_tree_route("TREE1", 10.0, 0.0)
    tree2 = _make_tree_route("TREE2", 10.0, 0.05)

    results = RoutingResults(
        compiled_routes={},
        tree_routes={"TREE1": tree1, "TREE2": tree2},
        failed_nets=[],
    )

    report = verify_clearance(results, min_clearance=0.127, backend=backend)

    assert report.total_checks == 1
    assert report.violation_count == 1


@pytest.mark.parametrize("backend", ["rust", "auto"])
def test_verify_clearance_checks_compiled_against_tree_routed(backend):
    """A compiled_routes net and a tree_routes net must be checked against
    each other too, not just within their own dict."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    compiled = CompiledRoute("NET1", path1, 0.2, [], None)
    tree = _make_tree_route("NET2", 10.0, 0.05)

    results = RoutingResults(
        compiled_routes={"NET1": compiled},
        tree_routes={"NET2": tree},
        failed_nets=[],
    )

    report = verify_clearance(results, min_clearance=0.127, backend=backend)

    assert report.total_checks == 1
    assert report.violation_count == 1


@pytest.mark.parametrize("backend", ["rust", "auto"])
def test_manifest_hv_fix_reaches_rust_and_auto_backends(backend):
    """The manifest-HV requirement reaches both compatibility selectors.
    See docs/evidence/2026-07-27-clearance-copper-balance.md Part B.2.

    Fails before the fix (required == 0.127mm via rust/auto for a
    DC_BUS_RTN-vs-gnd pair); passes after (required == 14.0mm, matching
    the pinned pre-migration oracle -- see ``verify_route_clearance``'s new optional
    ``hv_net_names`` parameter and ``clearance_check.py``'s
    ``_verify_clearance_rust``, which now passes
    ``_load_manifest_hv_net_names()`` through).

    Skipped (not xfailed) if elec/domain_manifest.yaml is unavailable or
    does not declare DC_BUS_RTN under HV, same reasoning as the sibling
    same environment assumptions as the test above.
    """
    pytest.importorskip("temper_drc_rs", reason="temper_drc_rs not built")
    from temper_placer.router_v6.clearance_check import _load_manifest_hv_net_names

    hv_nets = _load_manifest_hv_net_names()
    if "DC_BUS_RTN" not in hv_nets:
        pytest.skip(
            "elec/domain_manifest.yaml not found or does not declare "
            "DC_BUS_RTN under HV in this environment"
        )

    path1 = RoutePath("DC_BUS_RTN", [(0, 0), (10, 0)], "F.Cu", 10.0)
    route1 = CompiledRoute("DC_BUS_RTN", path1, 0.127, [], None)
    path2 = RoutePath("gnd", [(0, 0.05), (10, 0.05)], "F.Cu", 10.0)
    route2 = CompiledRoute("gnd", path2, 0.127, [], None)
    results = RoutingResults(
        compiled_routes={"DC_BUS_RTN": route1, "gnd": route2}, failed_nets=[]
    )

    report = verify_clearance(results, min_clearance=0.127, backend=backend)

    assert report.violation_count == 1
    required = report.violations[0].required_clearance
    assert required > 1.0, (
        f"DC_BUS_RTN vs gnd via backend={backend!r} should require IEC "
        f"60335 mains clearance, got {required}mm (looks like the "
        f"0.127mm default -- the manifest fix did not reach this backend)"
    )


def test_hb_gnd_is_present_in_manifest_hv_nets():
    """The retained Rust adapter receives the canonical HV manifest entry."""
    from temper_placer.router_v6.clearance_check import _load_manifest_hv_net_names

    assert "hb-gnd" in _load_manifest_hv_net_names()


# -----------------------------------------------------------------------------
# 2026-08-13: hyphen-boundary net-classification defect ("Family C" -- see
# PR #1145/#1162's "Family A"/"Family B" fixes elsewhere in this repo).
# The HV keyword matcher anchored word boundaries on
# "_" and start/end-of-string only, never "-", even though 85 of the 162
# real net names on the production board contain a hyphen. See
# docs/evidence/2026-08-13-hyphen-boundary-clearance-creepage-defect.md.
# -----------------------------------------------------------------------------


def test_hyphen_is_now_a_word_boundary_for_hv_keyword_match():
    """A hyphenated net that should match an HV keyword now does."""
    assert _is_hv_keyword_match("X-AC")
    assert _is_hv_keyword_match("HV-BUS")
    assert _is_hv_keyword_match("MAINS-LIVE")
    # Underscore boundary is unaffected.
    assert _is_hv_keyword_match("X_AC")


def test_hyphen_boundary_does_not_over_match_hv_keyword():
    """A keyword not adjacent to any boundary character must still not
    match, hyphen present in the name or not (mirrors PR #1162's
    equivalent guard for Family A/B)."""
    assert not _is_hv_keyword_match("TRACE-1")
    assert not _is_hv_keyword_match("TYPE-SPEED")  # "PE" substring, no boundary
    assert not _is_hv_keyword_match("XHVX-Y")


@pytest.mark.parametrize("net_name", ["X-AC", "HV-BUS", "MAINS-LINE"])
def test_production_clearance_hyphenated_hv_names_require_hv_spacing(net_name):
    """The live Rust production path recognizes hyphen-separated HV names."""
    hv_path = RoutePath(net_name, [(0, 0), (10, 0)], "F.Cu", 10.0)
    signal_path = RoutePath("SIGNAL", [(0, 1), (10, 1)], "F.Cu", 10.0)
    results = RoutingResults(
        compiled_routes={
            net_name: CompiledRoute(net_name, hv_path, 0.127, [], None),
            "SIGNAL": CompiledRoute("SIGNAL", signal_path, 0.127, [], None),
        },
        failed_nets=[],
    )

    report = verify_clearance(results, min_clearance=0.127)

    assert report.total_checks == 1
    assert report.violation_count == 1
    assert report.violations[0].required_clearance > 1.0


@pytest.mark.parametrize(
    "net_name",
    [
        "safety-line",
        "safety.ocp-line",
        "safety.ocp2-line",
        "safety.ovp-line",
        "safety.thermal-line",
        "safety.coil_thermal-line",
        "safety.uvlo_logic-line",
    ],
)
def test_production_clearance_selv_line_overrides_keep_default_spacing(net_name):
    """The exact confirmed-SELV denylist wins before ``LINE`` matching."""
    selv_path = RoutePath(net_name, [(0, 0), (10, 0)], "F.Cu", 10.0)
    signal_path = RoutePath("SIGNAL", [(0, 1), (10, 1)], "F.Cu", 10.0)
    results = RoutingResults(
        compiled_routes={
            net_name: CompiledRoute(net_name, selv_path, 0.127, [], None),
            "SIGNAL": CompiledRoute("SIGNAL", signal_path, 0.127, [], None),
        },
        failed_nets=[],
    )

    report = verify_clearance(results, min_clearance=0.127)

    assert report.total_checks == 1
    assert report.violation_count == 0


def test_selv_line_nets_stay_selv_after_hyphen_widening():
    """The one confirmed over-match this fix has to guard against: 14
    real, confirmed-SELV nets ending in a hyphenated "-line" suffix must
    NOT flip to HV via the widened "LINE" keyword match. See
    `_SELV_LINE_NET_OVERRIDES` in clearance_check.py."""
    for name in (
        "safety-line",
        "safety-line-1",
        "safety-line-7",
        "safety.ocp-line",
        "safety.ocp2-line",
        "safety.ovp-line",
        "safety.thermal-line",
        "safety.coil_thermal-line",
        "safety.uvlo_logic-line",
    ):
        assert not _is_hv_keyword_match(name.upper()), name
    # But a genuinely-HV net that merely happens to end in "-line" must
    # still match -- the override is a literal-name denylist, not a
    # blanket "-line" exemption.
    assert _is_hv_keyword_match("MAINS-LINE")
