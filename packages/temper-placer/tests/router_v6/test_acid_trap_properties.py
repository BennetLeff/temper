"""Property-based domain-correctness tests for acid trap detection.

Covers
------
* **R4 — Severity monotonicity:** ``_classify_severity(angle, trace_width)``
  returns the correct classification for a known set of angles and widths.
* **R5 — Trace-width monotonicity:** wider traces produce ≤ traps than
  narrow traces for identical geometry.

Also includes explicit scenario tests (TS1–TS4) from the DFM
property-tests plan (`docs/plans/2026-06-25-dfm-property-tests-plan.md`).
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.acid_trap_detection import (
    _classify_severity,
    detect_acid_traps,
)
from temper_placer.router_v6.astar_core import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from tests.router_v6.dfm_property_strategies import realistic_routing_results

# ---------------------------------------------------------------------------
# Shared settings
# ---------------------------------------------------------------------------

_SETTINGS = settings(
    max_examples=100,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)

# Known angle set for severity classification testing (from the plan).
_KNOWN_ANGLES: tuple[float, ...] = (
    30.0, 44.0, 45.0, 52.0, 60.0, 75.0, 89.0, 90.0, 120.0,
)
_KNOWN_WIDTHS: tuple[float, ...] = (0.1, 0.2, 0.5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _path_with_angle(
    angle_deg: float,
    segment_len: float = 10.0,
) -> list[tuple[float, float]]:
    """Return a 3-point path whose interior angle at p2 equals *angle_deg*.

    Uses the symmetric construction from ``test_acid_trap_boundary``:
        p1 = (-L, 0),  p2 = (0, 0),  p3 = (L·cos θ, L·sin θ)
    where θ = π − angle_rad, so that the angle between vectors
    ``p1−p2`` and ``p3−p2`` is exactly *angle_deg*.
    """
    theta = math.pi - math.radians(angle_deg)
    p3 = (segment_len * math.cos(theta), segment_len * math.sin(theta))
    return [(-segment_len, 0.0), (0.0, 0.0), p3]


def _make_single_route_results(
    angle_deg: float,
    width_mm: float = 0.2,
    net_name: str = "TEST",
) -> RoutingResults:
    """Build ``RoutingResults`` with a single 3-point path at *angle_deg*."""
    coords = _path_with_angle(angle_deg)
    path = RoutePath(
        net_name=net_name,
        coordinates=coords,
        layer_name="F.Cu",
        path_length=float(len(coords) * 10.0),
    )
    route = CompiledRoute(
        net_name=net_name,
        path=path,
        width_mm=width_mm,
        vias=[],
        matched_length_mm=None,
    )
    return RoutingResults(compiled_routes={net_name: route}, failed_nets=[])


# ===================================================================
# R4 — Severity classification monotonicity
# ===================================================================


@given(
    angle=st.sampled_from(_KNOWN_ANGLES),
    width=st.sampled_from(_KNOWN_WIDTHS),
)
@_SETTINGS
def test_classify_severity_matches_contract(angle: float, width: float) -> None:
    """``_classify_severity`` returns the correct category for known angles.

    Contract (from the module docstring):

    * angle < 45° → ``"high"`` (demoted to ``"medium"`` if width < 0.2 mm)
    * 45° ≤ angle < 60° → ``"medium"`` (demoted to ``"low"`` if width < 0.2 mm)
    * angle ≥ 60° → ``"low"`` (never demoted)
    """
    result = _classify_severity(angle, width)

    if width < 0.2:
        # Narrow trace — severity is demoted by one level.
        if angle < 45:
            expected = "medium"
        else:
            expected = "low"
    else:
        # Normal / wide trace — no demotion.
        if angle < 45:
            expected = "high"
        elif angle < 60:
            expected = "medium"
        else:
            expected = "low"

    assert result == expected, (
        f"angle={angle}°, width={width} mm: "
        f"expected {expected!r}, got {result!r}"
    )


@given(
    angle=st.sampled_from(_KNOWN_ANGLES),
    width=st.sampled_from(_KNOWN_WIDTHS),
)
@_SETTINGS
def test_detect_acid_traps_classifies_correctly(
    angle: float,
    width: float,
) -> None:
    """End-to-end: ``detect_acid_traps`` produces correct severity for
    known-angle paths.

    For angles ≥ 90° no trap is generated (the detection threshold is
    90°).  For smaller angles a trap is emitted whose severity matches
    ``_classify_severity``.
    """
    results = _make_single_route_results(angle, width)
    report = detect_acid_traps(results)

    if angle >= 90.0:
        assert report.trap_count == 0, (
            f"angle={angle}° must NOT produce a trap (threshold is 90°)"
        )
        return

    assert report.trap_count >= 1, (
        f"angle={angle}° must produce at least one trap"
    )

    expected_severity = _classify_severity(angle, width)
    for trap in report.acid_traps:
        assert trap.severity == expected_severity, (
            f"angle={angle}°, width={width} mm: "
            f"expected severity {expected_severity!r}, got {trap.severity!r}"
        )


# ===================================================================
# R5 — Trace-width monotonicity
# ===================================================================


@given(results=realistic_routing_results())
@_SETTINGS
def test_wider_trace_produces_fewer_or_equal_traps(
    results: RoutingResults,
) -> None:
    """Wider traces produce ≤ acid traps than narrow traces for identical
    geometry.

    Generates realistic routing results, then creates two copies with
    all trace widths fixed to 0.15 mm (narrow) and 0.5 mm (wide).
    Because acid-trap **detection** is based purely on angle < 90°
    (width only affects *severity*, not detection), the trap count must
    be identical.  The ≤ assertion is defensive against future
    width-dependent filtering.
    """
    # ---- Build narrow version (all widths = 0.15 mm) -----------------------
    narrow_routes: dict[str, CompiledRoute] = {}
    for name, route in results.compiled_routes.items():
        narrow_routes[name] = CompiledRoute(
            net_name=route.net_name,
            path=route.path,
            width_mm=0.15,
            vias=route.vias,
            matched_length_mm=route.matched_length_mm,
        )
    narrow_results = RoutingResults(
        compiled_routes=narrow_routes,
        failed_nets=list(results.failed_nets),
    )

    # ---- Build wide version (all widths = 0.5 mm) --------------------------
    wide_routes: dict[str, CompiledRoute] = {}
    for name, route in results.compiled_routes.items():
        wide_routes[name] = CompiledRoute(
            net_name=route.net_name,
            path=route.path,
            width_mm=0.5,
            vias=route.vias,
            matched_length_mm=route.matched_length_mm,
        )
    wide_results = RoutingResults(
        compiled_routes=wide_routes,
        failed_nets=list(results.failed_nets),
    )

    narrow_report = detect_acid_traps(narrow_results)
    wide_report = detect_acid_traps(wide_results)

    assert wide_report.trap_count <= narrow_report.trap_count, (
        f"Wider traces ({wide_report.trap_count} traps) must not have "
        f"more traps than narrow traces ({narrow_report.trap_count} traps)"
    )


# ===================================================================
# Explicit test scenarios (TS1–TS4 from the plan)
# ===================================================================


# --- TS1: 30° angle → "high" severity ---------------------------------------

@pytest.mark.parametrize("width", [0.2, 0.3, 0.5])
def test_ts1_30_degree_angle_high_severity(width: float) -> None:
    """TS1: 30° angle is classified as ``"high"`` for normal-width traces."""
    results = _make_single_route_results(30.0, width)
    report = detect_acid_traps(results)
    assert report.trap_count == 1
    assert report.acid_traps[0].severity == "high"
    assert report.critical_count == 1


# --- TS2: 50° angle — width demotion ----------------------------------------

def test_ts2_50_degree_angle_width_demotion() -> None:
    """TS2: 50° angle → ``"medium"`` at 0.2 mm, ``"low"`` at 0.1 mm."""
    # Normal width → medium (45° ≤ 50° < 60°, no demotion)
    results = _make_single_route_results(50.0, 0.2)
    report = detect_acid_traps(results)
    assert report.trap_count == 1
    assert report.acid_traps[0].severity == "medium"

    # Narrow width → demoted to low
    results_narrow = _make_single_route_results(50.0, 0.1)
    report_narrow = detect_acid_traps(results_narrow)
    assert report_narrow.trap_count == 1
    assert report_narrow.acid_traps[0].severity == "low"


# --- TS3: 65° angle → "low" regardless of width -----------------------------

@pytest.mark.parametrize("width", [0.1, 0.2, 0.5])
def test_ts3_65_degree_angle_low_severity(width: float) -> None:
    """TS3: 65° angle is always ``"low"``, regardless of trace width."""
    results = _make_single_route_results(65.0, width)
    report = detect_acid_traps(results)
    assert report.trap_count == 1
    assert report.acid_traps[0].severity == "low"


# --- TS4: 90° angle → no trap -----------------------------------------------

def test_ts4_90_degree_angle_no_trap() -> None:
    """TS4: 90° angle is not detected as an acid trap."""
    results = _make_single_route_results(90.0, 0.2)
    report = detect_acid_traps(results)
    assert report.trap_count == 0
