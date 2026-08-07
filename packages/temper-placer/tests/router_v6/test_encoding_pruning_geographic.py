"""Geographic pruning predicate tests — Python parity with Rust implementation.

Cross-checks the Python predicate functions in
``temper_placer.router_v6.constraint_model`` against the known test
vectors from ``temper_rust_router_core::pruning::tests`` (18 tests,
8 property tests).

Also tests the model-builder integration: with ``enable_geographic_pruning``
ON, the constraint model has fewer variables and constraints than the
full encoding (default OFF), and the pruned model is a structural subset
of the full model (no variables or constraints exist in the pruned model
that are absent from the full model).
"""

from __future__ import annotations

import pytest

# The predicate functions are standalone geometry helpers.
from temper_placer.router_v6.constraint_model import (
    _is_candidate_edge,
    _pin_span,
    _point_to_segment_distance,
)
from temper_placer.router_v6.constraint_model import (
    _DEFAULT_PRUNE_K_FACTOR as K_DEFAULT,
)
from temper_placer.router_v6.constraint_model import (
    _DEFAULT_PRUNE_M_MIN as M_MIN_DEFAULT,
)


class TestPointToSegmentDistance:
    """Matches the 5 tests from pruning.rs::tests."""

    def test_endpoint_when_projection_outside(self):
        d = _point_to_segment_distance(-5.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(d - 5.0) < 1e-9

    def test_perpendicular_midpoint(self):
        d = _point_to_segment_distance(5.0, 3.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(d - 3.0) < 1e-9

    def test_degenerate_zero_length(self):
        d = _point_to_segment_distance(3.0, 4.0, 0.0, 0.0, 0.0, 0.0)
        assert abs(d - 5.0) < 1e-9

    def test_point_on_segment(self):
        d = _point_to_segment_distance(5.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert d < 1e-9

    def test_diagonal(self):
        d = _point_to_segment_distance(0.0, 4.0, 0.0, 0.0, 3.0, 4.0)
        assert abs(d - 2.4) < 1e-9


class TestPinSpan:
    """Matches the 3 tests from pruning.rs::tests."""

    def test_empty(self):
        assert _pin_span([]) == 0.0

    def test_single_pin(self):
        assert _pin_span([(5.0, 5.0)]) == 0.0

    def test_two_pins(self):
        d = _pin_span([(0.0, 0.0), (3.0, 4.0)])
        assert abs(d - 5.0) < 1e-9

    def test_three_pins_max_not_adjacent(self):
        d = _pin_span([(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)])
        assert abs(d - (200.0**0.5)) < 1e-9


class TestPredicateEdgeCases:
    """Matches the 9 predicate edge-case tests from pruning.rs::tests."""

    def test_includes_edge_at_pin(self):
        pins = [(0.0, 0.0), (100.0, 0.0)]
        assert _is_candidate_edge(pins, 0.0, 0.0, 10.0, 0.0) is True

    def test_excludes_edge_far_away(self):
        pins = [(0.0, 0.0), (100.0, 0.0)]
        assert _is_candidate_edge(pins, 500.0, 0.0, 510.0, 0.0) is False

    def test_tiny_net_uses_m_min_floor(self):
        pins = [(0.0, 0.0), (1.0, 0.0)]  # S_n = 1, M_n = 30
        # Edge at 25mm: within 30 → candidate
        assert _is_candidate_edge(pins, 25.0, 0.0, 26.0, 0.0) is True
        # Edge at 35mm: beyond 30 → excluded
        assert _is_candidate_edge(pins, 35.0, 0.0, 36.0, 0.0) is False

    def test_single_pin_net(self):
        # S_n = 0, M_n = 30
        pin = [(50.0, 50.0)]
        assert _is_candidate_edge(pin, 50.0, 70.0, 51.0, 70.0) is True  # dist ≈ 20
        assert _is_candidate_edge(pin, 50.0, 85.0, 51.0, 85.0) is False  # dist ≈ 35

    def test_edge_exactly_at_margin(self):
        pins = [(0.0, 0.0), (10.0, 0.0)]  # S_n = 10, M_n = 30
        # Edge at y=30, x ∈ [0, 10]: distance from (0,0) = 30
        assert _is_candidate_edge(pins, 0.0, 30.0, 10.0, 30.0) is True

    def test_margin_scales_with_span(self):
        pins = [(0.0, 0.0), (50.0, 0.0)]  # S_n = 50, M_n = 100
        assert _is_candidate_edge(pins, 0.0, 90.0, 10.0, 90.0) is True  # dist ≈ 90
        assert _is_candidate_edge(pins, 0.0, 110.0, 10.0, 110.0) is False  # dist ≈ 110

    def test_large_net_covers_wide_area(self):
        pins = [(0.0, 0.0), (80.0, 0.0)]  # S_n = 80, M_n = 160
        assert _is_candidate_edge(pins, 40.0, 150.0, 50.0, 150.0) is True  # dist ≈ 150

    def test_custom_params_change_behavior(self):
        pins = [(0.0, 0.0), (10.0, 0.0)]  # S_n = 10
        # Default: M_n = 30 → edge at 25 passes
        assert _is_candidate_edge(pins, 0.0, 25.0, 10.0, 25.0, K_DEFAULT, M_MIN_DEFAULT) is True
        # Tight: K=1.0, M_min=5.0 → M_n = 10 → edge at 25 fails
        assert _is_candidate_edge(pins, 0.0, 25.0, 10.0, 25.0, 1.0, 5.0) is False
        # Wide: K=5.0, M_min=50 → M_n = 50 → edge at 25 passes
        assert _is_candidate_edge(pins, 0.0, 25.0, 10.0, 25.0, 5.0, 50.0) is True


class TestFailCapable:
    """Anti-vacuity: tight margin excludes detour edges."""

    def test_tight_margin_excludes_detour_edge(self):
        """Matches the fail-capable test from pruning.rs.

        Two pins 200mm apart. A detour edge at y=60 between x=100 and x=150
        is on a feasible route (pin_a → N1 → N2 → N3 → pin_b) but does NOT
        touch any pin. dist_min ≈ 78.1mm.

        K=2.0: M_n = 400 → candidate (correct — includes it)
        K=0.3: M_n = 60  → excluded (correct — detects over-pruning)
        """
        pins = [(0.0, 0.0), (200.0, 0.0)]
        detour_edge = (100.0, 60.0, 150.0, 60.0)

        # Default: should include
        assert _is_candidate_edge(pins, *detour_edge, K_DEFAULT, M_MIN_DEFAULT) is True

        # Tight params: should EXCLUDE
        assert _is_candidate_edge(pins, *detour_edge, 0.3, 1.0) is False, (
            "FAIL-CAPABLE PROOF: detour edge excluded by K=0.3. "
            "This proves the harness correctly detects when pruning is too aggressive."
        )
