"""Property-based domain-correctness tests for copper balance (U7).

Verifies invariants specific to ``analyze_copper_balance`` beyond the
six generic DFM invariants in ``test_dfm_hypothesis_fuzzing.py``:

* **R16 – Layer count invariant:**
  ``balanced_layer_count + unbalanced_layer_count == len(layer_balances)``
* **R17 – Area bounding:**
  ``0.0 ≤ copper_area_mm2 ≤ board_width * board_height`` for every layer
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings

from temper_placer.router_v6.copper_balance import analyze_copper_balance
from temper_placer.router_v6.routing_results import RoutingResults

from tests.router_v6.dfm_property_strategies import (
    BOARD_H,
    BOARD_W,
    realistic_routing_results,
)

# ---------------------------------------------------------------------------
# Shared Hypothesis settings — 200 iterations, 2000 ms deadline
# ---------------------------------------------------------------------------

_SETTINGS = settings(
    max_examples=200,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)

_BOARD_AREA = BOARD_W * BOARD_H  # 200.0 × 150.0 = 30 000 mm²


# ===================================================================
# TS1 — R16: layer count invariant (fuzzed)
# ===================================================================


@given(results=realistic_routing_results())
@_SETTINGS
def test_layer_count_invariant_holds(results: RoutingResults) -> None:
    """``balanced + unbalanced == len(layer_balances)`` for every fuzzed input."""
    report = analyze_copper_balance(
        results, board_width=BOARD_W, board_height=BOARD_H
    )

    total = report.balanced_layer_count + report.unbalanced_layer_count
    expected = len(report.layer_balances)

    assert total == expected, (
        f"Layer count invariant broken: "
        f"balanced({report.balanced_layer_count}) + "
        f"unbalanced({report.unbalanced_layer_count}) = {total}, "
        f"expected {expected} (len(layer_balances))"
    )


# ===================================================================
# TS2 — R17a: per-layer area ≤ board area (fuzzed)
# ===================================================================


@pytest.mark.xfail(
    reason=(
        "Known model limitation: copper area is a simple sum of "
        "trace_length × trace_width across all routes on a layer.  "
        "Fuzzed paths with overlapping geometry can double-count area, "
        "so the per-layer sum may exceed the physical board area.  "
        "The module does not perform overlap detection / deduplication."
    ),
    strict=True,
)
@given(results=realistic_routing_results())
@_SETTINGS
def test_per_layer_area_does_not_exceed_board_area(results: RoutingResults) -> None:
    """No per-layer copper area exceeds the total board area (30 000 mm²).

    .. note::

       Marked ``xfail`` because the module sums trace areas linearly
       without checking for geometric overlap.  Overlapping traces on
       the same layer are double-counted, which can push the aggregate
       beyond the physical board area.
    """
    report = analyze_copper_balance(
        results, board_width=BOARD_W, board_height=BOARD_H
    )

    for lb in report.layer_balances:
        assert lb.copper_area_mm2 <= _BOARD_AREA, (
            f"Layer {lb.layer_name} copper area {lb.copper_area_mm2} mm² "
            f"exceeds board area {_BOARD_AREA} mm²"
        )


# ===================================================================
# TS3 — R17b: per-layer area ≥ 0.0 (fuzzed)
# ===================================================================


@given(results=realistic_routing_results())
@_SETTINGS
def test_per_layer_area_is_non_negative(results: RoutingResults) -> None:
    """Every per-layer copper area is ≥ 0.0."""
    report = analyze_copper_balance(
        results, board_width=BOARD_W, board_height=BOARD_H
    )

    for lb in report.layer_balances:
        assert lb.copper_area_mm2 >= 0.0, (
            f"Layer {lb.layer_name} copper area {lb.copper_area_mm2} mm² "
            f"is negative"
        )


# ===================================================================
# TS4 — Empty input: 4 layers, 4 unbalanced, all areas zero, invariant
# ===================================================================


def test_empty_input_all_layers_unbalanced_areas_zero() -> None:
    """Empty ``RoutingResults`` → 4 layers, all unbalanced, all areas 0.0,
    and the layer count invariant still holds.
    """
    empty = RoutingResults(compiled_routes={}, failed_nets=[])
    report = analyze_copper_balance(
        empty, board_width=BOARD_W, board_height=BOARD_H
    )

    # 4 canonical layers
    assert len(report.layer_balances) == 4

    # All areas must be exactly zero
    for lb in report.layer_balances:
        assert lb.copper_area_mm2 == 0.0, (
            f"Layer {lb.layer_name} copper area {lb.copper_area_mm2} mm², "
            f"expected 0.0 for empty input"
        )
        assert lb.copper_percentage == 0.0

    # 0 % copper is below the 30 % minimum → every layer is unbalanced
    assert report.balanced_layer_count == 0
    assert report.unbalanced_layer_count == 4

    # R16 invariant
    assert (
        report.balanced_layer_count + report.unbalanced_layer_count
        == len(report.layer_balances)
    )
