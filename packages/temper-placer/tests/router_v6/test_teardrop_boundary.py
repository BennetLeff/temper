"""
Boundary edge-case tests for Router V6 teardrop generation module.

Covers via diameter boundaries, trace width boundaries, teardrop ratio
boundaries, via-to-trace ratio threshold, layer mismatch, and empty input.

Part of temper-q5dh (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
import warnings

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.teardrop_generation import (
    Teardrop,
    insert_teardrops,
)
from temper_placer.router_v6.via_placement import Via
from tests.router_v6.dfm_boundary_constants import (
    exactly_at,
    just_above,
    just_below,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

_NORMAL_TRACE_WIDTH = 0.127
_NORMAL_VIA_DIAMETER = 0.6
_NORMAL_VIA_DRILL = 0.3
_NORMAL_PATH_LAYER = "F.Cu"


def _make_path(
    coords=None,
    layer=_NORMAL_PATH_LAYER,
) -> RoutePath:
    if coords is None:
        coords = [(0.0, 0.0), (10.0, 10.0)]
    length = math.hypot(
        coords[-1][0] - coords[0][0],
        coords[-1][1] - coords[0][1],
    )
    return RoutePath("NET1", coords, layer, length)


def _make_via(
    diameter=_NORMAL_VIA_DIAMETER,
    drill=_NORMAL_VIA_DRILL,
    position=(5.0, 5.0),
    from_layer="F.Cu",
    to_layer="B.Cu",
) -> Via:
    return Via(position, from_layer, to_layer, diameter, drill, "NET1")


def _make_results(
    trace_width=_NORMAL_TRACE_WIDTH,
    vias=None,
    path=None,
    net_name="NET1",
) -> RoutingResults:
    if vias is None:
        vias = [_make_via()]
    if path is None:
        path = _make_path()
    route = CompiledRoute(net_name, path, trace_width, vias, None)
    return RoutingResults(compiled_routes={net_name: route}, failed_nets=[])


def _call_safely(
    routing_results,
    **kwargs,
) -> tuple[object, list[warnings.WarningMessage]]:
    """Call insert_teardrops capturing warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = insert_teardrops(routing_results, **kwargs)
    return report, w


# ============================================================================
# 1. Via diameter boundaries
# ============================================================================

@pytest.mark.parametrize(
    "diameter,expect_teardrop,expect_warning",
    [
        # Zero / negative — guarded by via.diameter <= 0
        pytest.param(0.0, False, True, id="via_diameter_zero"),
        pytest.param(-0.1, False, True, id="via_diameter_negative"),
        # NaN — guarded by math.isnan()
        pytest.param(
            float("nan"),
            False,
            True,
            id="via_diameter_nan",
        ),
        # +inf — guarded by math.isfinite()
        pytest.param(
            float("inf"),
            False,
            True,
            id="via_diameter_inf",
        ),
        # -inf — guard via.diameter <= 0 is True, correctly skipped.
        pytest.param(-float("inf"), False, True, id="via_diameter_neg_inf"),
    ],
)
def test_via_diameter_boundary(diameter, expect_teardrop, expect_warning):
    """Via diameter edge cases: should skip or crash cleanly."""
    via = _make_via(diameter=diameter)
    results = _make_results(vias=[via])

    report, captured_warnings = _call_safely(results)

    if expect_teardrop:
        assert report.teardrop_count >= 1
    else:
        assert report.teardrop_count == 0

    if expect_warning:
        assert len(captured_warnings) >= 1
    else:
        assert len(captured_warnings) == 0


# ============================================================================
# 2. Trace width boundaries (combined with normal via)
# ============================================================================

@pytest.mark.parametrize(
    "trace_width,expect_teardrop",
    [
        # 0.0 width — threshold via.diameter >= 0.0 is True,
        # teardrop_width = min(0.36, 0.0) = 0.0.  Degenerate but no crash.
        pytest.param(0.0, True, id="trace_width_zero"),
        # Negative width — clamped to >= 0 via max(0.0, ...)
        pytest.param(-0.1, True, id="trace_width_negative"),
        # NaN — threshold NaN >= anything is False, no teardrop.
        pytest.param(float("nan"), False, id="trace_width_nan"),
        # +inf — threshold 0.6 >= inf is False, no teardrop.
        pytest.param(float("inf"), False, id="trace_width_inf"),
        # -inf — clamped to >= 0 via max(0.0, ...)
        pytest.param(-float("inf"), True, id="trace_width_neg_inf"),
    ],
)
def test_trace_width_boundary(trace_width, expect_teardrop):
    """Trace width edge cases with a normal via."""
    results = _make_results(trace_width=trace_width)

    report, _w = _call_safely(results)

    if expect_teardrop:
        assert report.teardrop_count >= 1
        td = report.teardrops[0]
        # Correct behaviour: dimensions must be non-negative and finite
        assert td.width_mm >= 0, f"width_mm={td.width_mm} should be >= 0"
        assert math.isfinite(td.width_mm), f"width_mm={td.width_mm} should be finite"
    else:
        assert report.teardrop_count == 0


# ============================================================================
# 3. Teardrop length ratio boundaries
# ============================================================================

@pytest.mark.parametrize(
    "ratio,expect_clamped,expected_ratio",
    [
        # Below min — clamped to 0.1 with warning
        pytest.param(0.0, True, 0.1, id="ratio_zero"),
        pytest.param(-0.5, True, 0.1, id="ratio_negative"),
        # Within range — accepted as-is
        pytest.param(0.1, False, 0.1, id="ratio_at_min"),
        pytest.param(0.5, False, 0.5, id="ratio_mid"),
        pytest.param(1.0, False, 1.0, id="ratio_at_max"),
        # Above max — clamped to 1.0 with warning
        pytest.param(2.0, True, 1.0, id="ratio_above_max"),
        # NaN — clamped to 0.1 (math.isnan guard)
        pytest.param(
            float("nan"),
            True,
            0.1,
            id="ratio_nan",
        ),
    ],
)
def test_teardrop_length_ratio_boundary(ratio, expect_clamped, expected_ratio):
    """Teardrop length ratio edge cases: should clamp or crash cleanly."""
    results = _make_results()

    report, captured_warnings = _call_safely(
        results,
        teardrop_length_ratio=ratio,
    )

    # A teardrop should be produced in all cases (via is large enough)
    assert report.teardrop_count >= 1
    td = report.teardrops[0]

    if expect_clamped:
        # The module should emit a warning when it clamps
        assert len(captured_warnings) >= 1, (
            f"Expected a clamping warning for ratio={ratio!r}"
        )
        # Length should equal clamped ratio * via_diameter
        assert td.length_mm == pytest.approx(expected_ratio * _NORMAL_VIA_DIAMETER)
    else:
        assert len(captured_warnings) == 0
        assert td.length_mm == pytest.approx(ratio * _NORMAL_VIA_DIAMETER)


# ============================================================================
# 4. Via-to-trace ratio threshold (via.diameter >= trace_width * 1.2)
# ============================================================================

@pytest.mark.parametrize(
    "via_diameter,expect_teardrop",
    [
        # Exactly at threshold
        pytest.param(
            exactly_at(_NORMAL_TRACE_WIDTH * 1.2),
            True,
            id="threshold_exact",
        ),
        # Just below — no teardrop
        pytest.param(
            just_below(_NORMAL_TRACE_WIDTH * 1.2),
            False,
            id="threshold_just_below",
        ),
        # Just above — teardrop
        pytest.param(
            just_above(_NORMAL_TRACE_WIDTH * 1.2),
            True,
            id="threshold_just_above",
        ),
    ],
)
def test_via_to_trace_ratio_threshold(via_diameter, expect_teardrop):
    """Teardrop is only generated when via.diameter >= trace_width * 1.2."""
    via = _make_via(diameter=via_diameter)
    results = _make_results(vias=[via], trace_width=_NORMAL_TRACE_WIDTH)

    report, _w = _call_safely(results)

    if expect_teardrop:
        assert report.teardrop_count == 1
    else:
        assert report.teardrop_count == 0


# ============================================================================
# 5. Layer matching (via on different layer from path)
# ============================================================================

@pytest.mark.parametrize(
    "path_layer,via_from,via_to,expect_teardrop",
    [
        # Path matches from_layer
        pytest.param("F.Cu", "F.Cu", "B.Cu", True, id="match_from_layer"),
        # Path matches to_layer
        pytest.param("B.Cu", "F.Cu", "B.Cu", True, id="match_to_layer"),
        # Path on unrelated layer
        pytest.param("In1.Cu", "F.Cu", "B.Cu", False, id="mismatch_unrelated"),
        # Path on None layer (via compiled route with no layer_name attr)
        # This case is tested separately below.
    ],
)
def test_layer_matching(path_layer, via_from, via_to, expect_teardrop):
    """Teardrop generation respects layer matching between path and via."""
    path = _make_path(layer=path_layer)
    via = _make_via(from_layer=via_from, to_layer=via_to)
    results = _make_results(vias=[via], path=path)

    report, _w = _call_safely(results)

    if expect_teardrop:
        assert report.teardrop_count == 1
    else:
        assert report.teardrop_count == 0


def test_path_without_layer_name_skips():
    """A path object without a layer_name attribute yields no teardrop."""
    path = _make_path()
    # Simulate a path object that lacks layer_name (e.g. non-standard type)
    object.__setattr__(path, "layer_name", None)  # already None, but explicit

    via = _make_via(from_layer="F.Cu", to_layer="B.Cu")
    results = _make_results(vias=[via], path=path)

    report, _w = _call_safely(results)
    assert report.teardrop_count == 0


# ============================================================================
# 6. Empty input
# ============================================================================

def test_zero_vias_yields_no_teardrops():
    """No vias → no teardrops (even with via teardrops enabled)."""
    path = _make_path()
    results = _make_results(vias=[], path=path)

    report, _w = _call_safely(results, enable_via_teardrops=True)
    assert report.teardrop_count == 0


def test_zero_routes_yields_no_teardrops():
    """Empty compiled_routes → no teardrops."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])

    report, _w = _call_safely(results, enable_via_teardrops=True)
    assert report.teardrop_count == 0
    assert report.via_teardrop_count == 0
    assert report.pad_teardrop_count == 0


# ============================================================================
# 7. Single-coordinate path (no segment to infer direction)
# ============================================================================

def test_single_coordinate_path_skips():
    """A path with fewer than 2 coordinates cannot infer direction."""
    path = _make_path(coords=[(5.0, 5.0)])
    via = _make_via(position=(5.0, 5.0))
    results = _make_results(vias=[via], path=path)

    report, _w = _call_safely(results)
    assert report.teardrop_count == 0


def test_coincident_via_and_path_skips():
    """Via position coincident with nearest path coordinate → no direction."""
    # Place the via exactly at one coordinate, and the "neighbour" also
    # at the same point so dist ≈ 0.
    path = _make_path(coords=[(5.0, 5.0), (5.0, 5.0)])
    via = _make_via(position=(5.0, 5.0))
    results = _make_results(vias=[via], path=path)

    report, _w = _call_safely(results)
    assert report.teardrop_count == 0
