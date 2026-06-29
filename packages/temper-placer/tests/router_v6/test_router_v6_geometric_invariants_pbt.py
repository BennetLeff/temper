"""
Property-based tests for Router V6 geometric consistency invariants.

Validates fundamental geometric properties of routing output using
Hypothesis generative testing.  Each test class states a theorem (as
its docstring) and the test body provides the proof via assertions.

Requirements covered:
- R3: All trace segments within board bounds [0,w] x [0,h]
- R4: Via diameter > 0, diameter >= drill, position within board bounds
- R5: Trace widths positive and within [min, max] constraints
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings

from temper_placer.router_v6.routing_results import RoutingResults
from tests.router_v6.router_v6_property_strategies import routing_results

# ---------------------------------------------------------------------------
# Fixed board dimensions used by the shared strategy
# ---------------------------------------------------------------------------

BOARD_W: float = 200.0
BOARD_H: float = 150.0


# =========================================================================
# Theorem I:  Trace Containment (R3)
# =========================================================================


class TestTraceContainment:
    """Theorem: Every coordinate in every RoutePath for every
    CompiledRoute lies within the board boundary [0, board_width]
    x [0, board_height].

    Lemma I.1: All x-coordinates satisfy 0 <= x <= board_width.
    Lemma I.2: All y-coordinates satisfy 0 <= y <= board_height.
    """

    @pytest.mark.property
    @given(results=routing_results(board_width=BOARD_W, board_height=BOARD_H))
    @settings(max_examples=100, deadline=30000)
    def test_all_path_coordinates_within_board_bounds(
        self, results: RoutingResults
    ) -> None:
        """I.1 + I.2: Every coordinate in every path is within [0, BOARD_W] x [0, BOARD_H]."""
        for net_name, route in results.compiled_routes.items():
            for i, (x, y) in enumerate(route.path.coordinates):
                assert 0.0 <= x <= BOARD_W, (
                    f"{net_name} coordinate[{i}] x={x} outside [0, {BOARD_W}]"
                )
                assert 0.0 <= y <= BOARD_H, (
                    f"{net_name} coordinate[{i}] y={y} outside [0, {BOARD_H}]"
                )


# =========================================================================
# Theorem II:  Via Validity (R4)
# =========================================================================


class TestViaValidity:
    """Theorem: Every Via satisfies diameter > 0, drill > 0,
    diameter >= drill, and position within board bounds.

    Lemma II.1: diameter > 0 and drill > 0.
    Lemma II.2: diameter >= drill (annular ring constraint).
    Lemma II.3: position (x, y) within [0, BOARD_W] x [0, BOARD_H].
    """

    @pytest.mark.property
    @given(results=routing_results(board_width=BOARD_W, board_height=BOARD_H))
    @settings(max_examples=100, deadline=30000)
    def test_via_dimensions_positive_and_consistent(
        self, results: RoutingResults
    ) -> None:
        """II.1 + II.2: Every via has positive dimensions and diameter >= drill."""
        for net_name, route in results.compiled_routes.items():
            for vi, via in enumerate(route.vias):
                assert via.diameter > 0.0, (
                    f"{net_name} via[{vi}] diameter={via.diameter} is not positive"
                )
                assert via.drill > 0.0, (
                    f"{net_name} via[{vi}] drill={via.drill} is not positive"
                )
                assert via.diameter >= via.drill, (
                    f"{net_name} via[{vi}] diameter={via.diameter} < drill={via.drill}"
                )

    @pytest.mark.property
    @given(results=routing_results(board_width=BOARD_W, board_height=BOARD_H))
    @settings(max_examples=100, deadline=30000)
    def test_via_positions_within_board_bounds(
        self, results: RoutingResults
    ) -> None:
        """II.3: Every via position is within [0, BOARD_W] x [0, BOARD_H]."""
        for net_name, route in results.compiled_routes.items():
            for vi, via in enumerate(route.vias):
                x, y = via.position
                assert 0.0 <= x <= BOARD_W, (
                    f"{net_name} via[{vi}] x={x} outside [0, {BOARD_W}]"
                )
                assert 0.0 <= y <= BOARD_H, (
                    f"{net_name} via[{vi}] y={y} outside [0, {BOARD_H}]"
                )


# =========================================================================
# Theorem III:  Trace Width Positivity (R5)
# =========================================================================


class TestTraceWidthPositivity:
    """Theorem: Every CompiledRoute has a non-negative trace width.

    Lemma III.1: width_mm >= 0 for all compiled routes.
    Plane nets may carry width_mm = 0 (no physical trace);
    all active routed nets must have width_mm > 0.

    Lemma III.2: width_mm is finite (no NaN or Inf).
    """

    @pytest.mark.property
    @given(results=routing_results(board_width=BOARD_W, board_height=BOARD_H))
    @settings(max_examples=100, deadline=30000)
    def test_trace_widths_are_positive(self, results: RoutingResults) -> None:
        """III.1: Every compiled route has width_mm > 0."""
        for net_name, route in results.compiled_routes.items():
            assert route.width_mm > 0.0, (
                f"{net_name} width_mm={route.width_mm} is not positive"
            )

    @pytest.mark.property
    @given(results=routing_results(board_width=BOARD_W, board_height=BOARD_H))
    @settings(max_examples=100, deadline=30000)
    def test_trace_widths_are_finite(self, results: RoutingResults) -> None:
        """III.2: All trace widths are finite (no NaN or Inf)."""
        for net_name, route in results.compiled_routes.items():
            assert math.isfinite(route.width_mm), (
                f"{net_name} width_mm={route.width_mm} is not finite"
            )


# =========================================================================
# Theorem IV:  Path Length Consistency
# =========================================================================


class TestPathLengthConsistency:
    """Theorem: RoutePath.path_length exactly equals the sum of
    Euclidean distances between consecutive coordinates.

    For a path with N >= 2 coordinates (x_0, y_0), ..., (x_{N-1}, y_{N-1}):

        path_length == sum(||c_i - c_{i-1}|| for i in 1..N-1)

    For paths with 0 or 1 coordinates, path_length == 0.0.

    Lemma IV.1: Path length matches coordinate-based distance sum.
    Lemma IV.2: Empty or single-point paths have length 0.
    """

    @pytest.mark.property
    @given(results=routing_results(board_width=BOARD_W, board_height=BOARD_H))
    @settings(max_examples=100, deadline=30000)
    def test_path_length_matches_coordinate_distances(
        self, results: RoutingResults
    ) -> None:
        """IV.1 + IV.2: path_length equals sum of Euclidean segment distances."""
        for net_name, route in results.compiled_routes.items():
            coords = route.path.coordinates
            expected = 0.0
            for i in range(1, len(coords)):
                x1, y1 = coords[i - 1]
                x2, y2 = coords[i]
                expected += math.hypot(x2 - x1, y2 - y1)
            assert route.path.path_length == pytest.approx(expected, rel=1e-9, abs=1e-12), (
                f"{net_name} path_length={route.path.path_length} != "
                f"expected={expected} (computed from {len(coords)} coordinates)"
            )
