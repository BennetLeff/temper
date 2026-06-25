"""
Boundary edge-case tests for the annular ring check module (Stage 5.2).

Covers via geometry boundaries, ring threshold boundaries, at-threshold
ring values, layer-aware thresholds, and empty input.

Part of temper-j2xd (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
import warnings

import pytest

from temper_placer.router_v6.annular_ring_check import (
    AnnularRingReport,
    AnnularRingViolation,
    _check_via,
    check_annular_rings,
)
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.via_placement import Via
from tests.router_v6.dfm_boundary_constants import (
    VIA_DIAMETERS_DRILL_LARGER,
    VIA_DIAMETERS_EQUAL,
    VIA_DIAMETERS_NAN,
    VIA_DIAMETERS_NEGATIVE,
    VIA_DIAMETERS_ZERO,
    THRESHOLD_INF,
    THRESHOLD_NAN,
    THRESHOLD_NEGATIVE,
    THRESHOLD_ZERO,
    exactly_at,
    just_above,
    just_below,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_NORMAL_DIAMETER = 0.6
_NORMAL_DRILL = 0.3
_NORMAL_MIN_RING = 0.05
_NORMAL_MICROVIA_RING = 0.025
_NORMAL_NET = "TEST_NET"
_DEFAULT_POSITION = (5.0, 5.0)


def _make_via(
    diameter: float = _NORMAL_DIAMETER,
    drill: float = _NORMAL_DRILL,
    position: tuple[float, float] = _DEFAULT_POSITION,
    from_layer: str = "F.Cu",
    to_layer: str = "B.Cu",
    net_name: str = _NORMAL_NET,
    via_type: str | None = None,
) -> Via:
    """Create a Via with optional via_type override."""
    via = Via(position, from_layer, to_layer, diameter, drill, net_name)
    if via_type is not None:
        via.via_type = via_type  # type: ignore[attr-defined]
    return via


def _make_path(
    coords: list | None = None,
    layer: str = "F.Cu",
    net_name: str = _NORMAL_NET,
) -> RoutePath:
    """Create a RoutePath for CompiledRoute construction."""
    if coords is None:
        coords = [(0.0, 0.0), (10.0, 10.0)]
    length = math.hypot(
        coords[-1][0] - coords[0][0],
        coords[-1][1] - coords[0][1],
    )
    return RoutePath(net_name, coords, layer, length)


def _make_results(
    vias: list | None = None,
    net_name: str = _NORMAL_NET,
    trace_width: float = 0.127,
    path: RoutePath | None = None,
) -> RoutingResults:
    """Build RoutingResults containing a single route."""
    if vias is None:
        vias = [_make_via()]
    if path is None:
        path = _make_path(net_name=net_name)
    route = CompiledRoute(net_name, path, trace_width, vias, None)
    return RoutingResults(compiled_routes={net_name: route}, failed_nets=[])


# ============================================================================
# 1. Via diameter / drill boundaries
# ============================================================================


@pytest.mark.parametrize(
    "diameter,drill,expect_violation,expect_skip",
    [
        # ---- diameter zero ----
        # drill > 0, ring = (0.0 - 0.3)/2 = -0.15 <= threshold => violation
        pytest.param(0.0, 0.3, True, False, id="diameter_zero_drill_normal"),
        # ---- drill zero ----
        # drill <= 0 => skipped
        pytest.param(0.6, 0.0, False, True, id="drill_zero"),
        # ---- both zero ----
        # drill <= 0 => skipped
        pytest.param(0.0, 0.0, False, True, id="both_zero"),
        # ---- diameter negative ----
        # drill > 0, ring negative => violation
        pytest.param(-0.1, 0.3, True, False, id="diameter_negative"),
        # ---- drill negative ----
        # drill <= 0 => skipped
        pytest.param(0.6, -0.1, False, True, id="drill_negative"),
        # ---- both negative ----
        # drill <= 0 => skipped
        pytest.param(-0.1, -0.1, False, True, id="both_negative"),
        # ---- NaN diameter ----
        # drill > 0, ring = (NaN - drill)/2 = NaN; NaN <= threshold is False
        # => silently returns None (bug: should be caught by a guard or raise)
        pytest.param(
            float("nan"), 0.3, False, False,
            id="diameter_nan",
            marks=pytest.mark.xfail(
                reason="NaN diameter: drill guard passes (0.3 > 0), "
                "ring_width = NaN, NaN <= threshold is False; "
                "the via silently passes instead of being skipped or rejected."
            ),
        ),
        # ---- NaN drill ----
        # drill <= 0? NaN <= 0 is False => guard skipped.
        # ring = (0.6 - NaN)/2 = NaN, NaN <= threshold False => silently passes.
        pytest.param(
            0.6, float("nan"), False, False,
            id="drill_nan",
            marks=pytest.mark.xfail(
                reason="NaN drill: guard NaN <= 0 is False, so skip is missed; "
                "ring_width = NaN, NaN <= threshold is False; "
                "the via silently passes."
            ),
        ),
        # ---- both NaN ----
        pytest.param(
            float("nan"), float("nan"), False, False,
            id="both_nan",
            marks=pytest.mark.xfail(
                reason="NaN drill + diameter: all comparisons with NaN "
                "are False; the via silently passes."
            ),
        ),
        # ---- +inf diameter, normal drill ----
        # ring = (inf - 0.3)/2 = inf; inf <= 0.05 is False => passes.
        # Degenerate but no crash.
        pytest.param(float("inf"), 0.3, False, False, id="diameter_inf"),
        # ---- normal diameter, +inf drill ----
        # drill > 0, ring = (0.6 - inf)/2 = -inf; -inf <= 0.05 True => violation.
        pytest.param(0.6, float("inf"), True, False, id="drill_inf"),
        # ---- -inf diameter ----
        # drill > 0, ring = (-inf - 0.3)/2 = -inf => violation.
        pytest.param(-float("inf"), 0.3, True, False, id="diameter_neg_inf"),
        # ---- normal diameter, -inf drill ----
        # drill <= 0 => skipped (since -inf <= 0 is True)
        pytest.param(0.6, -float("inf"), False, True, id="drill_neg_inf"),
        # ---- diameter < drill (physically impossible but mathematically valid) ----
        # ring negative => violation
        pytest.param(0.3, 0.5, True, False, id="drill_larger_than_diameter"),
        # ---- diameter == drill ----
        # ring = 0.0 <= threshold => violation
        pytest.param(0.3, 0.3, True, False, id="diameter_equals_drill"),
    ],
)
def test_via_geometry_boundaries(
    diameter: float,
    drill: float,
    expect_violation: bool,
    expect_skip: bool,
) -> None:
    """Via diameter/drill edge cases: violations, skips, or silent passes.

    Uses ``_check_via`` directly to bypass the public validation layer.
    """
    via = _make_via(diameter=diameter, drill=drill)

    result = _check_via(via, _NORMAL_NET, _NORMAL_MIN_RING, _NORMAL_MICROVIA_RING)

    if expect_skip:
        # Guard clause hit: via skipped, result is None
        assert result is None, (
            f"Expected skip (None), got {result}"
        )
        return

    if expect_violation:
        assert isinstance(result, AnnularRingViolation), (
            f"Expected AnnularRingViolation, got {type(result).__name__}: {result}"
        )
        # For negative/inf ring widths the actual_ring_width will be odd,
        # but the violation should still be well-formed.
        assert result.net_name == _NORMAL_NET
        assert result.pad_diameter == diameter if not math.isnan(diameter) else True
        assert result.drill_diameter == drill if not math.isnan(drill) else True
    else:
        # Not skipped, not a violation => passed
        assert result is None, (
            f"Expected pass (None), got {result}"
        )


# ============================================================================
# 2. Ring threshold boundaries — public API validation
# ============================================================================


@pytest.mark.parametrize(
    "min_annular_ring,expect_raises",
    [
        # Zero — must be > 0 per spec
        pytest.param(0.0, True, id="threshold_zero"),
        # Negative (from boundary constants)
        pytest.param(-0.001, True, id="threshold_negative_small"),
        pytest.param(-1.0, True, id="threshold_negative_large"),
        # -inf — clearly <= 0
        pytest.param(-float("inf"), True, id="threshold_neg_inf"),
        # Normal positive value — should not raise
        pytest.param(0.05, False, id="threshold_normal_005"),
        pytest.param(0.127, False, id="threshold_normal_0127"),
        pytest.param(2.0, False, id="threshold_normal_2"),
        # Very small but positive — should not raise
        pytest.param(1e-6, False, id="threshold_tiny_positive"),
        # +inf — +inf <= 0 is False so validation passes.
        # All finite ring widths <= +inf => every via fails.
        pytest.param(float("inf"), False, id="threshold_inf"),
        # NaN — NaN <= 0 is False so validation passes.
        # Then NaN threshold makes every ring_width <= NaN False => zero violations.
        pytest.param(
            float("nan"), False,
            id="threshold_nan",
            marks=pytest.mark.xfail(
                reason="NaN passes the <= 0 validation guard (NaN <= 0 is False); "
                "then ring_width <= NaN is always False, so all vias silently "
                "pass.  NaN should be rejected at validation time."
            ),
        ),
    ],
)
def test_check_annular_rings_threshold_validation(
    min_annular_ring: float,
    expect_raises: bool,
) -> None:
    """``check_annular_rings`` input validation for *min_annular_ring*."""
    results = _make_results()

    if expect_raises:
        with pytest.raises(ValueError, match="min_annular_ring must be > 0"):
            check_annular_rings(results, min_annular_ring=min_annular_ring)
    else:
        # Should not raise
        report = check_annular_rings(results, min_annular_ring=min_annular_ring)
        assert isinstance(report, AnnularRingReport)


# ============================================================================
# 2b. Ring threshold boundaries — _check_via behaviour with exotic thresholds
# ============================================================================


@pytest.mark.parametrize(
    "threshold,expect_violation",
    [
        # threshold = 0.0: a normal via with ring=0.15 should pass (0.15 <= 0 False)
        pytest.param(0.0, False, id="check_via_threshold_zero"),
        # threshold = -0.001: 0.15 <= -0.001 False => passes
        pytest.param(-0.001, False, id="check_via_threshold_negative"),
        # threshold = +inf: 0.15 <= inf True => violation
        pytest.param(float("inf"), True, id="check_via_threshold_inf"),
        # threshold = -inf: 0.15 <= -inf False => passes
        pytest.param(-float("inf"), False, id="check_via_threshold_neg_inf"),
        # threshold = NaN: 0.15 <= NaN False => passes (silently)
        pytest.param(
            float("nan"), False,
            id="check_via_threshold_nan",
            marks=pytest.mark.xfail(
                reason="NaN threshold: ring_width <= NaN is always False, "
                "so vias that should fail are silently passed."
            ),
        ),
    ],
)
def test_check_via_threshold_boundaries(
    threshold: float,
    expect_violation: bool,
) -> None:
    """``_check_via`` behaviour when *min_annular_ring* is exotic.

    A via with ring = 0.15 mm is checked against the given threshold.
    """
    via = _make_via(diameter=0.6, drill=0.3)  # ring = 0.15 mm
    result = _check_via(via, _NORMAL_NET, threshold, _NORMAL_MICROVIA_RING)

    if expect_violation:
        assert isinstance(result, AnnularRingViolation)
        assert result.minimum_required == threshold
    else:
        assert result is None, (
            f"Expected pass (None), got {result}"
        )


# ---------------------------------------------------------------------------
# Also verify that a via with tiny ring is caught when threshold is normal
# but the same via is silently missed when threshold is NaN.
# ---------------------------------------------------------------------------
def test_tiny_ring_caught_with_normal_threshold() -> None:
    """Sanity: a via with ring=0.01 mm is caught at threshold=0.05."""
    via = _make_via(diameter=0.32, drill=0.3)  # ring = 0.01 mm
    result = _check_via(via, _NORMAL_NET, 0.05, _NORMAL_MICROVIA_RING)
    assert isinstance(result, AnnularRingViolation)


# ============================================================================
# 3. At-threshold rings
# ============================================================================
#
# The module uses a strict ``<=`` comparison (ring_width <= threshold).
# Due to IEEE-754 floating-point representation, a via whose nominal ring
# is *exactly* at the threshold may compute as slightly above it and thus
# pass unexpectedly.  The cases below use concrete diameter/drill pairs
# whose FP ring is known (see test-construction notes).


@pytest.mark.parametrize(
    "diameter,drill,expect_violation,threshold",
    [
        # ---- ring clearly below 0.05 (d=0.5 drill=0.4) ----
        # ring = (0.5 - 0.4)/2 ≈ 0.04999999999999999 < 0.05  => violation
        pytest.param(0.5, 0.4, True, 0.05, id="ring_below_005"),

        # ---- nominal ring = 0.05, but FP ring slightly above 0.05 ----
        # d=0.4 drill=0.3: computed ring ≈ 0.050000000000000017 > 0.05
        # The <= check was *intended* to catch this boundary case, but
        # floating-point representation pushes it just over the threshold.
        pytest.param(
            0.4, 0.3, True, 0.05,
            id="ring_exactly_at_005_nominal",
            marks=pytest.mark.xfail(
                reason="d=0.4 drill=0.3 yields FP ring ≈ 0.050000000000000017 "
                "which is > 0.05, so the <= check misses the boundary case. "
                "A tolerance-based comparison (e.g. ring <= threshold + ε) "
                "would catch this."
            ),
        ),

        # ---- ring clearly above 0.05 ----
        # d=0.6 drill=0.5: ring ≈ 0.04999999999999999 < 0.05  => violation
        # (need a pair that actually yields ring > 0.05)
        # d=0.4000000000000001 drill=0.3:
        #   ring ≈ 0.050000000000000044 > 0.05 => passes
        pytest.param(0.4000000000000001, 0.3, False, 0.05, id="ring_above_005"),

        # ---- ring clearly below 0.10 (d=0.6 drill=0.4) ----
        # ring = (0.6 - 0.4)/2 ≈ 0.09999999999999999 < 0.10 => violation
        pytest.param(0.6, 0.4, True, 0.10, id="ring_below_010"),

        # ---- nominal ring = 0.10, round-trip is FP-exact for these values ----
        # d=0.5 drill=0.3: FP ring = 0.10000000000000000555 == 0.10 in FP
        # The round-trip is exact because 2*0.1 + 0.3 = 0.5 (errors cancel).
        pytest.param(0.5, 0.3, True, 0.10, id="ring_exactly_at_010"),

        # ---- ring clearly above 0.10 ----
        # d=0.6 drill=0.3: ring = 0.15 > 0.10 => passes
        pytest.param(0.6, 0.3, False, 0.10, id="ring_above_010"),

        # ---- ring exactly zero (diameter == drill) ----
        # 0.0 <= threshold => violation
        pytest.param(0.3, 0.3, True, 0.05, id="ring_exactly_zero"),
    ],
)
def test_at_threshold_rings(
    diameter: float,
    drill: float,
    expect_violation: bool,
    threshold: float,
) -> None:
    """Verify boundary behaviour for ring widths at/near the threshold."""
    via = _make_via(diameter=diameter, drill=drill)
    result = _check_via(via, _NORMAL_NET, threshold, _NORMAL_MICROVIA_RING)

    if expect_violation:
        assert isinstance(result, AnnularRingViolation), (
            f"d={diameter} drill={drill} should violate at threshold={threshold} "
            f"(check uses <=), got {result}"
        )
    else:
        assert result is None, (
            f"d={diameter} drill={drill} should pass at threshold=0.05, "
            f"got {result}"
        )


# ============================================================================
# 4. Layer-aware thresholds
# ============================================================================


@pytest.mark.parametrize(
    "from_layer,to_layer,ring_width,min_ring,expect_violation",
    [
        # ---- external layers: full threshold ----
        # ring=0.03, threshold=0.05 => violation
        ("F.Cu", "B.Cu", 0.03, 0.05, True),
        # ring=0.06, threshold=0.05 => pass
        ("F.Cu", "B.Cu", 0.06, 0.05, False),
        # B.Cu only on one side
        ("B.Cu", "In1.Cu", 0.03, 0.05, True),
        ("In1.Cu", "B.Cu", 0.03, 0.05, True),
        # F.Cu only on one side
        ("F.Cu", "In1.Cu", 0.03, 0.05, True),
        # ---- internal layers: half threshold ----
        # ring=0.03, half threshold=0.025 => violation (0.03 <= 0.025? False => pass)
        ("In1.Cu", "In2.Cu", 0.03, 0.05, False),
        # ring=0.02, half threshold=0.025 => violation
        ("In1.Cu", "In2.Cu", 0.02, 0.05, True),
        # ring=0.025, half threshold=0.025 => violation (<= catches boundary)
        ("In1.Cu", "In2.Cu", 0.025, 0.05, True),
        ("In1.Cu", "In2.Cu", 0.025001, 0.05, False),
        # ---- layer names with .Cu suffix but not in EXTERNAL_LAYERS ----
        # These are treated as internal (0.5×)
        ("In3.Cu", "In4.Cu", 0.03, 0.05, False),
        # ---- unknown layer names (no .Cu, not in set) ----
        # getattr default "" => not external => internal => 0.5×
        # But this can't happen in practice; still test the resilience
    ],
)
def test_layer_aware_thresholds(
    from_layer: str,
    to_layer: str,
    ring_width: float,
    min_ring: float,
    expect_violation: bool,
) -> None:
    """External layers use full *min_annular_ring*; internal use 0.5×."""
    drill = 0.3
    diameter = 2.0 * ring_width + drill
    via = _make_via(
        diameter=diameter,
        drill=drill,
        from_layer=from_layer,
        to_layer=to_layer,
    )

    result = _check_via(via, _NORMAL_NET, min_ring, _NORMAL_MICROVIA_RING)

    if expect_violation:
        assert isinstance(result, AnnularRingViolation), (
            f"via {from_layer}→{to_layer} ring={ring_width} "
            f"should violate at min_ring={min_ring}"
        )
    else:
        assert result is None, (
            f"via {from_layer}→{to_layer} ring={ring_width} "
            f"should pass at min_ring={min_ring}"
        )


# ---------------------------------------------------------------------------
# 4b. Layer-aware thresholds — boundary ring values at the 0.5× multiplier
# ---------------------------------------------------------------------------
#
# Uses concrete diameter/drill pairs whose computed FP ring is verified
# relative to the threshold, avoiding round-trip construction issues.


@pytest.mark.parametrize(
    "diameter,drill,min_ring,expect_violation_external,expect_violation_internal",
    [
        # ---- ring ≈ 0.025, min_ring=0.05 ----
        # external threshold=0.05, internal threshold=0.025
        # d=0.35 drill=0.3: ring = (0.35-0.3)/2 = 0.025 exactly (powers of 2)
        # 0.025 <= 0.05 => violation (external)
        # 0.025 <= 0.025 => violation (internal, caught by <=)
        (0.35, 0.3, 0.05, True, True),

        # ---- ring ≈ 0.026, min_ring=0.05 ----
        # d=0.352 drill=0.3: ring = 0.026
        # external: 0.026 <= 0.05 => violation
        # internal: 0.026 <= 0.025 => passes
        (0.352, 0.3, 0.05, True, False),

        # ---- ring ≈ 0.024, min_ring=0.05 ----
        # d=0.348 drill=0.3: ring = 0.024
        # external: 0.024 <= 0.05 => violation
        # internal: 0.024 <= 0.025 => violation
        (0.348, 0.3, 0.05, True, True),

        # ---- ring ≈ 0.05, min_ring=0.05 ----
        # d=0.4 drill=0.3: FP ring ≈ 0.050000000000000017 > 0.05
        # external: passes (xfail — intended to be caught by <=)
        # internal: 0.050... <= 0.025 => passes (correct, ring > 0.025)
        pytest.param(
            0.4, 0.3, 0.05, True, False,
            id="ring_005_minring_005",
            marks=pytest.mark.xfail(
                reason="d=0.4 drill=0.3 yields FP ring ≈ 0.050000000000000017 "
                "which is > 0.05; the <= check misses the boundary case "
                "for the external layer."
            ),
        ),

        # ---- ring clearly above 0.05, min_ring=0.05 ----
        # d=0.6 drill=0.3: ring = 0.15
        # external: 0.15 <= 0.05 => passes
        # internal: 0.15 <= 0.025 => passes
        (0.6, 0.3, 0.05, False, False),

        # ---- ring ≈ 0.05, min_ring=0.1 ----
        # external threshold=0.1, internal threshold=0.05
        # d=0.4 drill=0.3: FP ring ≈ 0.050000000000000017
        # external: 0.050... <= 0.1 => violation
        # internal: 0.050... <= 0.05 => passes (xfail: ring > 0.05 in FP)
        pytest.param(
            0.4, 0.3, 0.1, True, True,
            id="ring_005_minring_010",
            marks=pytest.mark.xfail(
                reason="d=0.4 drill=0.3 yields FP ring ≈ 0.050000000000000017 "
                "which is > 0.05 (internal threshold for min_ring=0.1); "
                "the <= check misses the internal-layer boundary case."
            ),
        ),

        # ---- ring ≈ 0.051, min_ring=0.1 ----
        # d=0.402 drill=0.3: ring = (0.402-0.3)/2 = 0.051
        # external: 0.051 <= 0.1 => violation
        # internal: 0.051 <= 0.05 => passes
        (0.402, 0.3, 0.1, True, False),
    ],
)
def test_layer_aware_multiplier_boundaries(
    diameter: float,
    drill: float,
    min_ring: float,
    expect_violation_external: bool,
    expect_violation_internal: bool,
) -> None:
    """The 0.5× multiplier for internal layers works at threshold boundaries."""
    # External via
    via_ext = _make_via(diameter=diameter, drill=drill,
                        from_layer="F.Cu", to_layer="B.Cu")
    result_ext = _check_via(via_ext, _NORMAL_NET, min_ring, _NORMAL_MICROVIA_RING)
    if expect_violation_external:
        assert isinstance(result_ext, AnnularRingViolation), (
            f"external d={diameter} drill={drill} "
            f"should violate at min_ring={min_ring}"
        )
    else:
        assert result_ext is None, (
            f"external d={diameter} drill={drill} "
            f"should pass at min_ring={min_ring}"
        )

    # Internal via
    via_int = _make_via(diameter=diameter, drill=drill,
                        from_layer="In1.Cu", to_layer="In2.Cu")
    result_int = _check_via(via_int, _NORMAL_NET, min_ring, _NORMAL_MICROVIA_RING)
    if expect_violation_internal:
        assert isinstance(result_int, AnnularRingViolation), (
            f"internal d={diameter} drill={drill} "
            f"should violate at min_ring={min_ring}"
        )
    else:
        assert result_int is None, (
            f"internal d={diameter} drill={drill} "
            f"should pass at min_ring={min_ring}"
        )


# ============================================================================
# 5. Empty input
# ============================================================================


def test_empty_compiled_routes() -> None:
    """Zero vias from empty compiled_routes."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = check_annular_rings(results, min_annular_ring=0.05)

    assert report.total_vias_checked == 0
    assert report.violation_count == 0
    assert report.pass_rate == 100.0


def test_empty_compiled_routes_with_extra_vias_empty() -> None:
    """Empty compiled_routes + empty extra_vias list."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = check_annular_rings(
        results, min_annular_ring=0.05, extra_vias=[],
    )

    assert report.total_vias_checked == 0
    assert report.violation_count == 0


def test_route_with_zero_vias() -> None:
    """A compiled route with an empty via list."""
    path = _make_path()
    route = CompiledRoute(_NORMAL_NET, path, 0.127, [], None)
    results = RoutingResults(compiled_routes={_NORMAL_NET: route}, failed_nets=[])
    report = check_annular_rings(results, min_annular_ring=0.05)

    assert report.total_vias_checked == 0
    assert report.violation_count == 0
    assert report.pass_rate == 100.0


def test_extra_vias_only() -> None:
    """Vias supplied only via *extra_vias*, not in compiled_routes."""
    via = _make_via(diameter=0.6, drill=0.3)  # ring=0.15, should pass
    results = RoutingResults(compiled_routes={}, failed_nets=[])
    report = check_annular_rings(
        results, min_annular_ring=0.05, extra_vias=[via],
    )

    assert report.total_vias_checked == 1
    assert report.violation_count == 0


def test_pass_rate_with_zero_vias() -> None:
    """Pass rate is 100.0% when zero vias are checked."""
    report = AnnularRingReport(violations=[], total_vias_checked=0)
    assert report.pass_rate == 100.0


# ============================================================================
# Smoke: via_type = "microvia" uses its own threshold regardless of layer
# ============================================================================


def test_microvia_threshold_overrides_layer() -> None:
    """Microvia threshold (0.025 mm) overrides the external/internal threshold."""
    # ring = 0.03 mm.  External threshold = 0.05 => would fail.
    # Microvia threshold = 0.025 => 0.03 > 0.025 => passes.
    via = _make_via(
        diameter=0.36, drill=0.3,  # ring = 0.03
        from_layer="F.Cu", to_layer="B.Cu",
        via_type="microvia",
    )
    result = _check_via(via, _NORMAL_NET, 0.05, _NORMAL_MICROVIA_RING)
    assert result is None, "microvia with ring=0.03 should pass at microvia threshold 0.025"


def test_microvia_violation_caught() -> None:
    """Microvia with ring below microvia threshold is flagged."""
    # ring = 0.02 mm.  Microvia threshold = 0.025 => 0.02 <= 0.025 => violation.
    via = _make_via(
        diameter=0.34, drill=0.3,  # ring = 0.02
        from_layer="In1.Cu", to_layer="In2.Cu",
        via_type="microvia",
    )
    result = _check_via(via, _NORMAL_NET, 0.05, _NORMAL_MICROVIA_RING)
    assert isinstance(result, AnnularRingViolation)
    assert result.minimum_required == _NORMAL_MICROVIA_RING


# ============================================================================
# AnnularRingViolation / AnnularRingReport boundary values
# ============================================================================


def test_violation_deficiency_at_threshold() -> None:
    """Deficiency is zero when ring exactly equals the minimum."""
    v = AnnularRingViolation(
        net_name="N1",
        via_position=(0.0, 0.0),
        pad_diameter=0.4,
        drill_diameter=0.3,
        actual_ring_width=0.05,
        minimum_required=0.05,
    )
    assert v.deficiency == 0.0


def test_violation_deficiency_negative_ring() -> None:
    """Deficiency is correct when actual ring is negative."""
    v = AnnularRingViolation(
        net_name="N1",
        via_position=(0.0, 0.0),
        pad_diameter=0.3,
        drill_diameter=0.5,
        actual_ring_width=-0.1,
        minimum_required=0.05,
    )
    assert v.deficiency == pytest.approx(0.15)


def test_report_pass_rate_all_fail() -> None:
    """Pass rate is 0.0% when every via fails."""
    violations = [
        AnnularRingViolation("N1", (0.0, 0.0), 0.4, 0.35, 0.025, 0.1),
        AnnularRingViolation("N2", (1.0, 1.0), 0.4, 0.35, 0.025, 0.1),
    ]
    report = AnnularRingReport(violations=violations, total_vias_checked=2)
    assert report.pass_rate == 0.0


def test_report_pass_rate_all_pass() -> None:
    """Pass rate is 100.0% when no vias fail."""
    report = AnnularRingReport(violations=[], total_vias_checked=10)
    assert report.pass_rate == 100.0
