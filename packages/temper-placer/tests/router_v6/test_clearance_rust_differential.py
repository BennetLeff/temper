"""Differential test: Rust `verify_clearance(backend="rust")` vs the Python
reference `verify_clearance(backend="python")`.

Part of the 2026-07-26 clearance Rust port (see
docs/evidence/2026-07-26-clearance-rust-port.md). The port must produce
IDENTICAL violation sets to the pure-Python implementation -- not merely the
same count. This file asserts set-equality (same net pairs, same layers,
same actual/required clearance values) across:

  - every fixture already covered by test_clearance_boundary.py /
    test_clearance_induction.py / test_scale_resolution.py, re-run through
    both backends,
  - randomized property-based inputs at several sizes, HV fractions, and
    via/width distributions, including the falsifier scenario (all-HV,
    which degrades the Rust accelerator to brute force and must still match).

If ``temper_drc_rs`` is not installed, these tests are skipped rather than
failed -- the Python backend remains the documented fallback.
"""

from __future__ import annotations

import math
import random

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.clearance_check import _HAS_RUST_CLEARANCE, verify_clearance
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.via_placement import Via

pytestmark = pytest.mark.skipif(
    not _HAS_RUST_CLEARANCE, reason="temper_drc_rs.verify_route_clearance not available"
)

LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
HV_BASES = ["AC_L", "AC_N", "HV_BUS", "MAINS_LIVE"]
FINE_BASES = ["SIG_A", "SIG_B", "GND_1", "VCC_3V3", "SPI_CLK", "I2C_SDA", "PWM_OUT"]


def _make_route(net_name, coords, layer="F.Cu", width_mm=0.127, vias=None):
    length = 0.0
    for i in range(len(coords) - 1):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        length += math.hypot(dx, dy)
    return CompiledRoute(
        net_name=net_name,
        path=RoutePath(net_name=net_name, coordinates=list(coords), layer_name=layer, path_length=length),
        width_mm=width_mm,
        vias=list(vias) if vias else [],
        matched_length_mm=None,
    )


def _random_routing_results(rng: random.Random, n_routes: int, hv_fraction: float):
    routes = {}
    voltage_ratings = {}
    for i in range(n_routes):
        is_hv = rng.random() < hv_fraction
        base = rng.choice(HV_BASES if is_hv else FINE_BASES)
        net_name = f"{base}_{i}"
        if is_hv:
            voltage_ratings[net_name] = rng.uniform(20.0, 400.0)

        layer = rng.choice(LAYERS)
        n_segs = rng.randint(1, 5)
        x, y = rng.uniform(0, 40), rng.uniform(0, 40)
        coords = [(x, y)]
        for _ in range(n_segs):
            x = min(40.0, max(0.0, x + rng.uniform(-6, 6)))
            y = min(40.0, max(0.0, y + rng.uniform(-6, 6)))
            coords.append((x, y))

        vias = []
        if rng.random() < 0.25:
            to_layer = rng.choice(LAYERS)
            vias.append(
                Via(
                    position=coords[-1],
                    from_layer=layer,
                    to_layer=to_layer,
                    diameter=rng.uniform(0.3, 0.8),
                    drill=0.3,
                    net_name=net_name,
                )
            )

        width = rng.uniform(0.1, 2.0)
        routes[net_name] = _make_route(net_name, coords, layer=layer, width_mm=width, vias=vias)

    return RoutingResults(compiled_routes=routes, failed_nets=[]), voltage_ratings


def _violation_set(report, tol=1e-6):
    """Canonicalize a ClearanceReport's violations into a comparable set.

    Compares net pair (unordered -- the backends may report net1/net2 in
    either order for a tie-free pair, though in practice both iterate
    routes in the same dict order and should agree exactly), layer, and
    rounded actual/required clearance. Deliberately excludes `location`:
    on exact-distance ties between multiple candidate segment pairs, the
    two backends may legitimately pick different (but equally valid)
    closest points -- ties are not expected in these fixtures, but this
    keeps the comparison robust rather than fragile.
    """
    out = set()
    for v in report.violations:
        pair = frozenset({v.net1, v.net2})
        out.add(
            (
                pair,
                v.layer,
                round(v.actual_clearance / tol) * tol,
                round(v.required_clearance / tol) * tol,
            )
        )
    return out


def _assert_same_results(rr, min_clearance=0.127, voltage_ratings=None, msg=""):
    py_report = verify_clearance(rr, min_clearance=min_clearance, voltage_ratings=voltage_ratings, backend="python")
    rust_report = verify_clearance(rr, min_clearance=min_clearance, voltage_ratings=voltage_ratings, backend="rust")

    assert py_report.total_checks == rust_report.total_checks, (
        f"{msg}: total_checks mismatch py={py_report.total_checks} rust={rust_report.total_checks}"
    )
    py_set = _violation_set(py_report)
    rust_set = _violation_set(rust_report)
    assert py_set == rust_set, (
        f"{msg}: violation sets differ.\n"
        f"  python-only: {py_set - rust_set}\n"
        f"  rust-only:   {rust_set - py_set}\n"
        f"  python count={len(py_report.violations)} rust count={len(rust_report.violations)}"
    )


# ---------------------------------------------------------------------------
# Deterministic fixtures mirroring the existing hand-written test scenarios.
# ---------------------------------------------------------------------------


def test_empty_input():
    rr = RoutingResults(compiled_routes={}, failed_nets=[])
    _assert_same_results(rr, msg="empty")


def test_single_route():
    rr = RoutingResults(
        compiled_routes={"A": _make_route("A", [(0.0, 0.0), (10.0, 0.0)])}, failed_nets=[]
    )
    _assert_same_results(rr, msg="single_route")


def test_overlapping_segments():
    rr = RoutingResults(
        compiled_routes={
            "NET1": _make_route("NET1", [(0.0, 0.0), (10.0, 0.0)], width_mm=0.5),
            "NET2": _make_route("NET2", [(0.0, 0.1), (10.0, 0.1)], width_mm=0.5),
        },
        failed_nets=[],
    )
    _assert_same_results(rr, msg="overlapping_segments")


def test_hv_both_hv():
    rr = RoutingResults(
        compiled_routes={
            "HV_BUS": _make_route("HV_BUS", [(0.0, 0.0), (10.0, 0.0)]),
            "AC_L": _make_route("AC_L", [(0.0, 0.5), (10.0, 0.5)]),
        },
        failed_nets=[],
    )
    _assert_same_results(rr, voltage_ratings={"HV_BUS": 100.0, "AC_L": 400.0}, msg="hv_both_hv")


def test_via_to_trace():
    via = Via(position=(5.0, 5.0), from_layer="F.Cu", to_layer="B.Cu", diameter=0.6, drill=0.3, net_name="A")
    rr = RoutingResults(
        compiled_routes={
            "A": _make_route("A", [(0.0, 0.0), (10.0, 10.0)], vias=[via]),
            "B": _make_route("B", [(5.0, 0.0), (5.0, 10.0)]),
        },
        failed_nets=[],
    )
    _assert_same_results(rr, msg="via_to_trace")


def test_multilayer_via_path():
    from temper_placer.router_v6.astar_core import RoutePath3D

    path = RoutePath3D(
        net_name="A",
        segments=[(0.0, 0.0, "F.Cu"), (5.0, 5.0, "F.Cu"), (5.0, 5.0, "In1.Cu"), (10.0, 10.0, "In1.Cu")],
        via_positions=[(5.0, 5.0)],
        path_length=20.0,
    )
    route_a = CompiledRoute(net_name="A", path=path, width_mm=0.2, vias=[], matched_length_mm=None)
    rr = RoutingResults(
        compiled_routes={
            "A": route_a,
            "B": _make_route("B", [(5.0, 0.0), (5.0, 10.0)], layer="In1.Cu"),
        },
        failed_nets=[],
    )
    _assert_same_results(rr, msg="multilayer_via_path")


# ---------------------------------------------------------------------------
# Randomized / property-based differential sweep.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(30))
def test_random_small(seed):
    rng = random.Random(seed * 1000 + 1)
    n = rng.randint(2, 25)
    hv_fraction = rng.choice([0.0, 0.02, 0.1, 0.3])
    rr, voltage_ratings = _random_routing_results(rng, n, hv_fraction)
    min_clearance = rng.choice([0.127, 0.5, 2.0])
    _assert_same_results(
        rr, min_clearance=min_clearance, voltage_ratings=voltage_ratings, msg=f"seed={seed} n={n}"
    )


def test_random_all_hv_falsifier():
    """Falsifier check: if every net is HV-gated, the Rust accelerator's
    FINE-FINE grid never engages (everything goes through the brute-force
    HV path) -- must still match Python exactly."""
    rng = random.Random(4242)
    rr, voltage_ratings = _random_routing_results(rng, 40, hv_fraction=1.0)
    _assert_same_results(rr, voltage_ratings=voltage_ratings, msg="all_hv_falsifier")


def test_random_dense_fine_only():
    """Stress the FINE-FINE grid specifically: no HV nets at all."""
    rng = random.Random(99)
    rr, voltage_ratings = _random_routing_results(rng, 80, hv_fraction=0.0)
    _assert_same_results(rr, voltage_ratings=voltage_ratings, msg="dense_fine_only")
