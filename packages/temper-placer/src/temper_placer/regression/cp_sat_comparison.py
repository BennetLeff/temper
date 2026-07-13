"""CP-SAT comparison primitives for regression testing.

Extracted from the now-retired parity test harness (U4).  These dataclasses
and functions survive as CP-SAT regression infrastructure — comparing CP-SAT
placements against each other (across solver parameter changes, model revisions,
or board updates), NOT against JAX.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
