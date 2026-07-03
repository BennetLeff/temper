"""U8: Parity Test Harness — CP-SAT vs JAX baseline comparison framework.

Builds a test harness that compares CP-SAT placements against JAX baseline
placements on the physics oracle, enabling the strangler cutover gate decision.

Requirements covered:
    R11 (strangler comparison), R7 (same oracle scoring), R9 (deletion gate condition)

Test scenarios:
    1. test_cp_sat_finds_feasible_placement — CP-SAT solves a synthetic board
    2. test_cp_sat_placement_passes_audit  — U4 audit passes on solved output
    3. test_score_placement_works_on_cp_sat_output — score_placement() consumes
       CP-SAT positions and returns structured metrics
    4. test_parity_harness_compares_metrics — comparison framework detects
       quality differences between two synthetic placements
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from temper_placer.placer.cp_sat.audit import audit_placement
from temper_placer.placer.cp_sat.model import (
    SolveStatus,
    build_cp_sat_model,
    solve_cp_sat_model,
)

# ============================================================================
# Synthetic fixture helpers
# ============================================================================

BOARD_W_MM = 100.0
BOARD_H_MM = 100.0


def _make_synthetic_components() -> dict[str, dict]:
    """Create synthetic component dicts for CP-SAT model building.

    Returns a dict compatible with ``build_cp_sat_model()``.
    The same ref strings are used in the Netlist for scoring.
    """
    return {
        "R1": {"width_mm": 1.6, "height_mm": 0.8},
        "C1": {"width_mm": 2.0, "height_mm": 1.2},
        "U1": {"width_mm": 5.0, "height_mm": 4.0},
        "Q1": {"width_mm": 10.0, "height_mm": 10.0},
    }


def _make_netlist_and_board():
    """Create Netlist and Board for ``score_placement()``.

    Returns:
        tuple of (Netlist, Board, hv_components, lv_components, thermal_components)
    """
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Net, Netlist, Pin

    components = [
        Component(
            ref="R1", footprint="0603", bounds=(1.6, 0.8),
            pins=[Pin("1", "1", (0, 0), net="NET1")],
            net_class="Signal",
        ),
        Component(
            ref="C1", footprint="0805", bounds=(2.0, 1.2),
            pins=[Pin("1", "1", (0, 0), net="NET2")],
            net_class="Signal",
        ),
        Component(
            ref="U1", footprint="SOIC-8", bounds=(5.0, 4.0),
            pins=[Pin("1", "1", (0, 0), net="NET3")],
            net_class="Signal",
        ),
        Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 10.0),
            pins=[Pin("1", "1", (0, 0), net="HV_BUS")],
            net_class="HighVoltage",
        ),
    ]
    nets = [
        Net("NET1", [("R1", "1")]),
        Net("NET2", [("C1", "1")]),
        Net("NET3", [("U1", "1")]),
        Net("HV_BUS", [("Q1", "1")]),
    ]
    netlist = Netlist(components=components, nets=nets)
    netlist.build_indices()

    board = Board(width=BOARD_W_MM, height=BOARD_H_MM)

    hv: set[str] = {"Q1"}
    lv: set[str] = {"R1", "C1", "U1"}
    thermal: set[str] = {"Q1"}

    return netlist, board, hv, lv, thermal


def _build_and_solve_cp_sat(
    components: dict[str, dict] | None = None,
    timeout_s: float = 10.0,
) -> tuple[dict[str, tuple[float, float]], SolveStatus]:
    """Helper: build CP-SAT model, solve, return (positions, status)."""
    if components is None:
        components = _make_synthetic_components()

    model, ctx = build_cp_sat_model(
        components=components,
        board_w_mm=BOARD_W_MM,
        board_h_mm=BOARD_H_MM,
        scale_factor=10,
    )

    # Add a soft wirelength objective so the solver has a direction
    refs = list(components.keys())
    net_pairs = [(refs[i], refs[i + 1]) for i in range(len(refs) - 1)]
    from temper_placer.placer.cp_sat.model import add_soft_wirelength_objective
    add_soft_wirelength_objective(model, ctx, net_pairs, spread_weight=1.0)

    result = solve_cp_sat_model(
        model, ctx,
        timeout_s=timeout_s,
        num_workers=4,
        log_progress=False,
    )

    return result.positions, result.status


# ============================================================================
# Per-metric comparison helpers
# ============================================================================


@dataclass
class MetricComparison:
    """Result of comparing a single metric between two placements.

    Attributes:
        name: Metric name (e.g., 'clearance_3mm').
        cp_sat_value: Value from the CP-SAT (or candidate) placement.
        jax_value: Value from the JAX (or baseline) placement.
        passed: True if the comparison condition is satisfied.
        detail: Human-readable comparison string.
    """

    name: str
    cp_sat_value: float
    jax_value: float
    passed: bool
    detail: str = ""


@dataclass
class ParityComparisonResult:
    """Aggregated result of a parity comparison across all metrics.

    Attributes:
        passed: True iff all per-metric comparisons pass.
        comparisons: List of per-metric MetricComparison objects.
        summary: Human-readable summary string.
    """

    passed: bool
    comparisons: list[MetricComparison] = field(default_factory=list)
    summary: str = ""


def compare_metric_dicts(
    candidate_scores: dict[str, Any],
    baseline_scores: dict[str, Any],
    *,
    wirelength_metric: str = "total_manhattan_wirelength",
) -> ParityComparisonResult:
    """Compare two score dicts per-metric and return a structured result.

    Comparison rules (Pareto-style gate):
      - Clearance metrics (clearance_3mm, clearance_6mm): candidate >= baseline
      - thermal_score: candidate >= baseline
      - wirelength (if present): candidate <= baseline (within 5% tolerance)
      - All others: higher-is-better by default

    Args:
        candidate_scores: Score dict from the candidate placer (e.g., CP-SAT).
        baseline_scores: Score dict from the baseline placer (e.g., JAX).
        wirelength_metric: Key in the score dict for wirelength.

    Returns:
        ParityComparisonResult with per-metric breakdown and overall pass/fail.
    """
    comparisons: list[MetricComparison] = []
    all_passed = True

    metrics = set(candidate_scores.keys()) & set(baseline_scores.keys())

    if wirelength_metric in metrics:
        metrics.discard(wirelength_metric)
        metrics.add(wirelength_metric)  # Put it last for output readability

    for metric_name in sorted(metrics):
        cand_val = float(candidate_scores.get(metric_name, 0.0))
        base_val = float(baseline_scores.get(metric_name, 0.0))

        if metric_name == wirelength_metric:
            # Lower is better, within 5% tolerance
            if base_val > 0:
                ratio = cand_val / base_val
                tolerance = 1.05
                passed = cand_val <= base_val * tolerance
            else:
                ratio = float("inf")
                passed = cand_val <= 0.0  # If baseline is 0, candidate must be 0 too

            detail = (
                f"{metric_name}: candidate={cand_val:.2f}, "
                f"baseline={base_val:.2f}, ratio={ratio:.3f}, "
                f"tolerance=1.05, passed={passed}"
            )
        else:
            # Higher is better (default for all oracle metrics)
            passed = cand_val >= base_val - 1e-9
            detail = (
                f"{metric_name}: candidate={cand_val:.4f}, "
                f"baseline={base_val:.4f}, delta={cand_val - base_val:.4f}, "
                f"passed={passed}"
            )

        comp = MetricComparison(
            name=metric_name,
            cp_sat_value=cand_val,
            jax_value=base_val,
            passed=passed,
            detail=detail,
        )
        comparisons.append(comp)
        if not passed:
            all_passed = False

    passed_metrics = sum(1 for c in comparisons if c.passed)
    total_metrics = len(comparisons)
    summary = (
        f"Parity comparison: {passed_metrics}/{total_metrics} metrics passed"
        if all_passed
        else (
            f"Parity FAILED: {passed_metrics}/{total_metrics} metrics passed. "
            f"Failing: {[c.name for c in comparisons if not c.passed]}"
        )
    )

    return ParityComparisonResult(
        passed=all_passed,
        comparisons=comparisons,
        summary=summary,
    )


# ============================================================================
# U8-T1: CP-SAT finds a feasible placement
# ============================================================================


class TestCpSatFindsFeasiblePlacement:
    """U8-T1: CP-SAT model solves successfully on a synthetic board."""

    def test_cp_sat_finds_feasible_placement(self):
        """Run CP-SAT on synthetic board, verify FEASIBLE or OPTIMAL status."""
        positions, status = _build_and_solve_cp_sat()

        assert status in (
            SolveStatus.FEASIBLE,
            SolveStatus.OPTIMAL,
        ), f"Expected FEASIBLE or OPTIMAL, got {status}"

        assert len(positions) == 4, (
            f"Expected positions for 4 components, got {len(positions)}"
        )
        for ref, (x, y) in positions.items():
            assert 0.0 <= x <= BOARD_W_MM, (
                f"{ref} x={x} out of board width [0, {BOARD_W_MM}]"
            )
            assert 0.0 <= y <= BOARD_H_MM, (
                f"{ref} y={y} out of board height [0, {BOARD_H_MM}]"
            )


# ============================================================================
# U8-T2: CP-SAT placement passes U4 audit
# ============================================================================


class TestCpSatPlacementAudit:
    """U8-T2: CP-SAT placement passes post-solve constraint audit."""

    def test_cp_sat_placement_passes_audit(self):
        """CP-SAT placement passes U4 no-overlap audit."""
        components = _make_synthetic_components()
        positions, status = _build_and_solve_cp_sat(components)

        assert status in (SolveStatus.FEASIBLE, SolveStatus.OPTIMAL), (
            f"Solve failed with {status}"
        )

        report = audit_placement(
            positions=positions,
            components=components,
            scale_factor=10,
            board_w_mm=BOARD_W_MM,
            board_h_mm=BOARD_H_MM,
        )

        assert report.passed, (
            f"Audit failed with {len(report.violations)} violations: "
            + "; ".join(v.detail for v in report.violations[:3])
        )
        assert report.stats["failed"] == 0, (
            f"Expected 0 failed checks, got {report.stats['failed']}"
        )
        assert report.stats["checked"] > 0, "Expected at least 1 audit check"


# ============================================================================
# U8-T3: Score placement works on CP-SAT output
# ============================================================================


class TestScorePlacementOnCpSat:
    """U8-T3: ``score_placement()`` consumes CP-SAT positions."""

    @pytest.mark.slow
    @pytest.mark.ci
    def test_score_placement_works_on_cp_sat_output(self):
        """Score a CP-SAT placement via score_placement(), verify expected keys."""
        from temper_placer.metrics.external_oracle import score_placement

        components = _make_synthetic_components()
        positions, status = _build_and_solve_cp_sat(components)
        assert status in (SolveStatus.FEASIBLE, SolveStatus.OPTIMAL), (
            f"Solve failed with {status}"
        )

        netlist, board, hv, lv, thermal = _make_netlist_and_board()

        result = score_placement(
            positions=positions,
            netlist=netlist,
            board=board,
            hv_components=hv,
            lv_components=lv,
            min_clearance=8.0,
            thermal_components=thermal,
            thermal_edge="BOTTOM",
            thermal_max_distance=10.0,
        )

        # Verify all expected keys are present
        expected_keys = {
            "hv_lv_clearance_score",
            "clearance_3mm",
            "clearance_6mm",
            "thermal_score",
            "zone_compliance_score",
            "compactness_score",
        }
        actual_keys = set(result.keys())
        missing = expected_keys - actual_keys
        assert not missing, f"Missing expected keys in score result: {missing}"

        # Verify score ranges
        for key in expected_keys:
            val = result[key]
            assert 0.0 <= val <= 1.0, (
                f"{key}={val} is outside [0, 1] range"
            )


# ============================================================================
# U8-T4: Parity harness compares metrics between two placements
# ============================================================================


class TestParityHarnessComparison:
    """U8-T4: The metric comparison framework detects differences."""

    @pytest.mark.slow
    @pytest.mark.ci
    @pytest.mark.comparison
    def test_parity_harness_compares_metrics(self):
        """Compare a good vs bad synthetic placement, detect quality delta."""
        from temper_placer.metrics.external_oracle import score_placement

        netlist, board, hv, lv, thermal = _make_netlist_and_board()

        # --- Good placement: components spread, Q1 near bottom edge ---
        good_positions: dict[str, tuple[float, float]] = {
            "Q1": (10.0, 5.0),    # Near bottom edge → good thermal
            "R1": (30.0, 40.0),   # Spread out for clearance
            "C1": (50.0, 60.0),
            "U1": (70.0, 30.0),
        }

        # --- Bad placement: Q1 far from edge, components clustered ---
        bad_positions: dict[str, tuple[float, float]] = {
            "Q1": (10.0, 85.0),   # Far from bottom edge → bad thermal
            "R1": (15.0, 80.0),   # Clustered near Q1 → clearance issues
            "C1": (12.0, 78.0),
            "U1": (18.0, 82.0),
        }

        good_scores = score_placement(
            positions=good_positions,
            netlist=netlist,
            board=board,
            hv_components=hv,
            lv_components=lv,
            min_clearance=8.0,
            thermal_components=thermal,
            thermal_edge="BOTTOM",
            thermal_max_distance=10.0,
        )

        bad_scores = score_placement(
            positions=bad_positions,
            netlist=netlist,
            board=board,
            hv_components=hv,
            lv_components=lv,
            min_clearance=8.0,
            thermal_components=thermal,
            thermal_edge="BOTTOM",
            thermal_max_distance=10.0,
        )

        # The good placement should have higher-or-equal scores on
        # clearance metrics and thermal_score
        for metric in ("clearance_3mm", "clearance_6mm", "thermal_score"):
            good_val = good_scores[metric]
            bad_val = bad_scores[metric]
            assert good_val >= bad_val - 1e-9, (
                f"Good placement scored lower than bad on {metric}: "
                f"{good_val:.4f} < {bad_val:.4f}"
            )

        # Run the comparison framework
        result = compare_metric_dicts(good_scores, bad_scores)

        # The comparison should report per-metric details
        assert len(result.comparisons) > 0, (
            "Expected at least 1 metric comparison"
        )
        assert result.summary, "Expected non-empty summary string"

        # Verify the comparison format: should have per-metric detail lines
        for comp in result.comparisons:
            assert comp.name in good_scores, (
                f"Comparison references unknown metric '{comp.name}'"
            )
            assert isinstance(comp.detail, str) and len(comp.detail) > 0, (
                f"Comparison for '{comp.name}' missing detail"
            )

        # Demonstrate the per-metric breakdown output (failure reproduction)
        comparison_lines = [c.detail for c in result.comparisons]
        # This is the format the parity test would emit on failure
        print("Per-metric comparison (good vs bad):")
        for line in comparison_lines:
            print(f"  {line}")
        print(f"  Summary: {result.summary}")
